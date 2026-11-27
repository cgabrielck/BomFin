"""Role card loading and strict prompt rendering.

Role cards are declarative YAML files. The harness, not the prompt text,
enforces tools and budgets; the prompt only describes the role.
"""
from pathlib import Path
import re
from typing import Annotated, Literal

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

PROMPT_ROOT = Path(__file__).parent / "prompts"
ROLE_NAME = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z][a-z_]{1,31}$")]
# Application-owned capabilities; YAML cannot grant additional tools.
READ_ONLY_TOOLS = frozenset({
    "resolve_symbols", "read_observations", "read_massive_snapshot",
    "read_bars", "compute_indicators", "read_quote_snapshot",
    "read_account", "read_risk_limits",
})


class RoleCardError(ValueError):
    """Role card is missing, malformed, or does not match its file name."""


class PromptRenderError(ValueError):
    """Prompt template failed to render (missing variable or bad syntax)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Budget(_Strict):
    max_input_tokens: Annotated[int, Field(ge=1)]
    max_output_tokens: Annotated[int, Field(ge=1)]
    max_attempts_per_node: Annotated[int, Field(ge=1, le=5)]
    deadline_seconds: Annotated[int, Field(ge=1)]


class PromptRef(_Strict):
    system: str
    user: str
    version: Annotated[int, Field(ge=1)]


class RoleCard(_Strict):
    version: Literal[1]
    role: ROLE_NAME
    purpose: Annotated[str, StringConstraints(min_length=1)]
    inputs: str
    outputs: str
    tools: Annotated[tuple[str, ...], Field(min_length=1)]
    forbidden: tuple[str, ...]
    budget: Budget
    prompt: PromptRef

    @model_validator(mode="after")
    def tools_are_unique_and_not_trading(self) -> "RoleCard":
        if len(set(self.tools)) != len(self.tools):
            raise ValueError("Duplicate tool names in role card")
        for tool in self.tools:
            if any(word in tool for word in ("order", "submit", "place", "trade", "intent")):
                raise ValueError(f"Execution-capable tool is not allowed for research roles: {tool}")
        if set(self.tools) - READ_ONLY_TOOLS:
            raise ValueError("Tool is not an application-approved read-only capability")
        return self


def load_role_card(name: str, roles_dir: Path) -> RoleCard:
    if re.fullmatch(r"[a-z][a-z_]{1,31}", name) is None:
        raise RoleCardError("Invalid role name")
    path = roles_dir / f"{name}.yaml"
    if not path.is_file():
        raise RoleCardError(f"Role card not found: {path.name}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RoleCardError(f"Invalid YAML in {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RoleCardError(f"Role card must be a mapping: {path.name}")
    try:
        card = RoleCard.model_validate(raw)
    except ValueError as exc:
        raise RoleCardError(f"Schema violation in {path.name}: {exc}") from exc
    if card.role != name:
        raise RoleCardError(f"Role '{card.role}' does not match file name '{name}'")
    return card


def load_all_role_cards(roles_dir: Path) -> dict[str, RoleCard]:
    names = sorted(p.stem for p in roles_dir.glob("*.yaml"))
    return {name: load_role_card(name, roles_dir) for name in names}


def _env(prompt_root: Path) -> Environment:
    # StrictUndefined: a missing variable is an error, never a silent blank.
    return Environment(
        loader=FileSystemLoader(str(prompt_root)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )


def render_prompt(card: RoleCard, kind: Literal["system", "user"], context: dict,
                  prompt_root: Path = PROMPT_ROOT) -> str:
    template_name = card.prompt.system if kind == "system" else card.prompt.user
    try:
        return _env(prompt_root).get_template(template_name).render(**context)
    except TemplateError as exc:
        raise PromptRenderError(f"{card.role}/{kind}: {exc}") from exc
