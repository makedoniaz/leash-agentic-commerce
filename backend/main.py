import os
from typing import Any, Literal

import openai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from mock_jobs import confirm_job, get_job, prepare_job, resolve_transaction
from policy_items import merge_duplicate_items
from policy_prompt import (
    build_policy_extraction_messages,
    detect_explicit_currency,
    detect_explicit_period_days,
)


Currency = Literal["CHF", "USD", "EUR"]
ProductCategory = Literal[
    "books",
    "clothing",
    "cosmetics",
    "dining",
    "electronics",
    "food_delivery",
    "fuel",
    "gift_card",
    "groceries",
    "home_improvement",
    "hotel",
    "household",
    "membership",
    "sporting_goods",
    "subscriptions",
    "transport",
]


class Spending(BaseModel):
    total_price_max: float | None = Field(default=None, gt=0)
    currency: Currency
    period_in_days: int | None = Field(default=None, gt=0)


class ProductItem(BaseModel):
    name: str = Field(min_length=1)
    category: ProductCategory
    quantity: int = Field(ge=1)
    max_price_per_item: float | None = Field(default=None, gt=0)


class Products(BaseModel):
    items: list[ProductItem] = Field(min_length=1)


class Merchant(BaseModel):
    blocklist: list[str] = Field(default_factory=list)
    allowlist: list[str] = Field(default_factory=list)


class OrderTerms(BaseModel):
    require_returnable: bool = True
    require_cancellable: bool = True


class WalletPolicy(BaseModel):
    raw_instructions: str = Field(min_length=1)
    products: Products
    spending: Spending
    merchant: Merchant
    order_terms: OrderTerms
    notes_for_customer: str = ""

    @model_validator(mode="after")
    def validate_spending_controls(self) -> "WalletPolicy":
        has_item_limit = any(
            item.max_price_per_item is not None for item in self.products.items
        )
        if self.spending.total_price_max is None and not has_item_limit:
            raise ValueError(
                "Provide a total-price limit or at least one item-price limit."
            )
        if (
            self.spending.period_in_days is not None
            and self.spending.total_price_max is None
        ):
            raise ValueError("A period can only be used with a total-price limit.")
        return self


class DraftSpending(BaseModel):
    total_price_max: float | None = None
    currency: Currency | None = None
    period_in_days: int | None = None


class DraftProductItem(BaseModel):
    name: str | None = None
    category: ProductCategory | None = None
    quantity: int | None = None
    max_price_per_item: float | None = None


class DraftProducts(BaseModel):
    items: list[DraftProductItem] | None = None


class DraftMerchant(BaseModel):
    blocklist: list[str] | None = None
    allowlist: list[str] | None = None


class DraftOrderTerms(BaseModel):
    require_returnable: bool | None = None
    require_cancellable: bool | None = None


class DraftWalletPolicy(BaseModel):
    raw_instructions: str
    products: DraftProducts
    spending: DraftSpending
    merchant: DraftMerchant
    order_terms: DraftOrderTerms
    notes_for_customer: str | None = ""


class PolicyRequest(BaseModel):
    wallet_id: int = Field(ge=0, le=31)
    policy_text: str = Field(min_length=1)
    additional_text: str | None = None


class PolicyResponse(BaseModel):
    walletId: int
    policy: dict[str, Any]
    missingFields: list[str]
    complete: bool


class PrepareJobRequest(BaseModel):
    wallet_id: int = Field(ge=0, le=31)
    policy: WalletPolicy


class ResolveTransactionRequest(BaseModel):
    decision: Literal["approve", "decline"]


app = FastAPI(
    title="Leash Agentic Commerce Demo",
    description="Public portfolio backend using generated, fictional transactions.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def identify() -> dict[str, str]:
    return {
        "service": "leash-agentic-commerce-demo",
        "data": "generated-fictional-only",
        "policy_parser": "local-ollama",
        "transaction_mode": "mock",
    }


def parse_with_ollama(text: str) -> DraftWalletPolicy:
    """Extract a policy with the user's local Ollama server; no cloud key is used."""
    client = openai.OpenAI(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        # The OpenAI client requires a non-empty value. Ollama ignores it.
        api_key="ollama-local",
    )
    completion = client.beta.chat.completions.parse(
        model=os.getenv("OLLAMA_MODEL", "llama3.2"),
        messages=build_policy_extraction_messages(text),
        response_format=DraftWalletPolicy,
        temperature=0,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise ValueError("The local Ollama model did not return a parsed policy.")

    # Keep critical values deterministic instead of allowing model guesses.
    parsed.spending.currency = detect_explicit_currency(text)
    parsed.spending.period_in_days = detect_explicit_period_days(text)
    return parsed


def check_missing_fields(draft: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    items = draft.get("products", {}).get("items") or []
    if not items:
        missing.append("products.items")
    for index, item in enumerate(items):
        if not item.get("name"):
            missing.append(f"products.items.{index}.name")
        if not item.get("category"):
            missing.append(f"products.items.{index}.category")
        if item.get("quantity") is None:
            missing.append(f"products.items.{index}.quantity")

    spending = draft.get("spending", {})
    has_item_limit = any(item.get("max_price_per_item") is not None for item in items)
    if spending.get("total_price_max") is None and not has_item_limit:
        missing.append("spending.total_price_max_or_item_limit")
    if spending.get("currency") is None:
        missing.append("spending.currency")
    if spending.get("period_in_days") is not None and spending.get("total_price_max") is None:
        missing.append("spending.total_price_max")
    return missing


@app.post("/parse-policy", response_model=PolicyResponse)
def parse_policy(request: PolicyRequest) -> PolicyResponse:
    combined_text = request.policy_text.strip()
    if request.additional_text:
        combined_text += f"\nAdditional constraints: {request.additional_text.strip()}"
    try:
        parsed = parse_with_ollama(combined_text)
    except openai.APIConnectionError as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cannot reach local Ollama. Start Ollama and run "
                "`ollama pull llama3.2`, then try again."
            ),
        ) from error
    except (openai.APIError, ValueError) as error:
        raise HTTPException(
            status_code=502,
            detail=f"Local Ollama policy extraction failed: {error}",
        ) from error

    draft = parsed.model_dump()
    products = draft.setdefault("products", {})
    products["items"] = merge_duplicate_items(products.get("items") or []) or None
    order_terms = draft.setdefault("order_terms", {})
    if order_terms.get("require_returnable") is None:
        order_terms["require_returnable"] = True
    if order_terms.get("require_cancellable") is None:
        order_terms["require_cancellable"] = True
    missing = check_missing_fields(draft)
    return PolicyResponse(
        walletId=request.wallet_id,
        policy=draft,
        missingFields=missing,
        complete=not missing,
    )


@app.post("/mock/jobs/prepare", status_code=201)
def prepare_mock_job(request: PrepareJobRequest) -> dict[str, Any]:
    return prepare_job(request.wallet_id, request.policy.model_dump())


@app.post("/mock/jobs/{job_id}/confirm", status_code=202)
def confirm_mock_job(job_id: str) -> dict[str, Any]:
    try:
        return confirm_job(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/mock/jobs/{job_id}")
def read_mock_job(job_id: str) -> dict[str, Any]:
    try:
        return get_job(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/mock/jobs/{job_id}/transactions/{transaction_id}/resolve")
def resolve_mock_transaction(
    job_id: str,
    transaction_id: str,
    request: ResolveTransactionRequest,
) -> dict[str, Any]:
    try:
        return resolve_transaction(job_id, transaction_id, request.decision)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
