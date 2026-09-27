import re
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from mock_jobs import confirm_job, get_job, prepare_job, resolve_transaction
from policy_items import merge_duplicate_items
from policy_prompt import detect_explicit_currency, detect_explicit_period_days


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
        "mode": "mock",
    }


_CATEGORY_KEYWORDS: tuple[tuple[ProductCategory, tuple[str, ...]], ...] = (
    ("sporting_goods", ("running shoe", "sports shoe", "water bottle", "football", "tennis")),
    ("books", ("book", "ebook", "audiobook")),
    ("electronics", ("monitor", "laptop", "computer", "phone", "headphone", "camera")),
    ("groceries", ("grocer", "ingredient", "vegetable", "fruit")),
    ("food_delivery", ("food delivery", "delivered meal")),
    ("dining", ("restaurant", "dinner", "lunch", "coffee")),
    ("clothing", ("shirt", "jacket", "dress", "clothing", "fashion shoe")),
    ("cosmetics", ("cosmetic", "makeup", "skincare", "perfume")),
    ("fuel", ("fuel", "petrol", "diesel", "charging")),
    ("gift_card", ("gift card", "voucher")),
    ("home_improvement", ("tool", "building supply", "renovation")),
    ("hotel", ("hotel", "accommodation")),
    ("household", ("furniture", "cleaning", "kitchenware")),
    ("membership", ("membership", "gym")),
    ("subscriptions", ("subscription", "streaming")),
    ("transport", ("train", "flight", "taxi", "transport", "ride")),
)


def _extract_category(text: str) -> tuple[str, ProductCategory]:
    lowered = text.casefold()
    for category, keywords in _CATEGORY_KEYWORDS:
        for keyword in keywords:
            if keyword in lowered:
                return keyword, category
    return "requested item", "household"


def _extract_quantity(text: str, item_name: str) -> int:
    words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
    }
    match = re.search(
        rf"\b(\d+|{'|'.join(words)})\s+(?:pairs?\s+of\s+)?{re.escape(item_name)}s?\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return 1
    raw = match.group(1).casefold()
    return int(raw) if raw.isdigit() else words[raw]


def _extract_amount(text: str) -> float | None:
    patterns = (
        r"(?i)(?:CHF|USD|EUR|SFr\.?|\$|€)\s*(\d+(?:[.,]\d{1,2})?)",
        r"(?i)(\d+(?:[.,]\d{1,2})?)\s*(?:CHF|USD|EUR|francs?|franks?|euros?|dollars?)",
        r"(?i)(?:under|up to|at most|maximum|max|budget(?: of)?)\s*(\d+(?:[.,]\d{1,2})?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1).replace(",", "."))
    return None


def parse_policy_text(text: str) -> dict[str, Any]:
    """Create an editable demo draft without any external API or private data."""
    item_name, category = _extract_category(text)
    currency = detect_explicit_currency(text)
    amount = _extract_amount(text)
    period = detect_explicit_period_days(text)
    lowered = text.casefold()
    draft = {
        "raw_instructions": text,
        "products": {
            "items": merge_duplicate_items(
                [
                    {
                        "name": item_name,
                        "category": category,
                        "quantity": _extract_quantity(text, item_name),
                        "max_price_per_item": None,
                    }
                ]
            )
        },
        "spending": {
            "total_price_max": amount,
            "currency": currency,
            "period_in_days": period,
        },
        "merchant": {"blocklist": [], "allowlist": []},
        "order_terms": {
            "require_returnable": "not returnable" not in lowered,
            "require_cancellable": "not cancellable" not in lowered,
        },
        "notes_for_customer": (
            "This public demo uses a deterministic local parser. Review the extracted rules before confirming."
        ),
    }
    return draft


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
    draft = parse_policy_text(combined_text)
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
