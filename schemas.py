from pydantic_ai import RunContext
from anthropic.types.beta.agent_create_params import Tool
from typing import Literal
import utils
from deps import Deps

from pydantic import BaseModel, Field, model_validator
from datetime import datetime, date


FilterType = Literal["eq", "ne", "lt", "le", "gt", "ge", "in"]
Scalar = int | float | str | datetime | date

class MeanSchema(BaseModel):
    """Base model schema to calculate the mean of a list of numbers"""

    numbers: list[int | float] = Field(
        ..., min_length=1, description="List of numbers to calculate mean"
    )


class GetTableSchema(BaseModel):
    """Base model schema get a Table"""

    table_name: str = Field(..., min_length=1, description="Table Name")


class FilterSchema(BaseModel):
    """Filter to apply to a stored ibis expression."""

    key: str = Field(
        ...,
        description="Key of the stored expression, returned by get_table or filter_table",
    )
    field: str = Field(..., min_length=1, description="Column to filter by")
    filter_type: FilterType = Field(
        ...,
        description=(
            "eq equal, ne not equal, lt lower than, le lower or equal, "
            "gt greater than, ge greater or equal, in one of a list of values"
        ),
    )
    value: Scalar | list[Scalar] = Field(
        ..., description="Single value, or a list of values when filter_type is 'in'"
    )

    @model_validator(mode="after")
    def _check_value_shape(self) -> "FilterSchema":
        is_list = isinstance(self.value, list)
        if self.filter_type == "in" and not is_list:
            raise ValueError("filter_type 'in' requires a list of values")
        if self.filter_type != "in" and is_list:
            raise ValueError(
                f"filter_type {self.filter_type!r} requires a single value, not a list"
            )
        return self


class GroupBySchema(BaseModel):
    """ Group By SQL equivalent using an already stored key. """

    key: str = Field(
        ..., description="Key of the stored expression, returned by get_table or filter_table"
    )
    group_by_columns: list[str] = Field(
        ..., min_length=1, description="The columns to group by"
    )
    aggregations: dict[str, Literal['count', 'sum', 'mean', 'unique', 'max', 'min']] = Field(
        ..., description="key value dictionary, the key is the column name, while the value is the aggregation operation to perform"
    )

class SelectSchema(BaseModel):
    """Select a group of columns from a stored ibis expression."""

    key: str = Field(
        ..., description="Key of the stored expression, returned by get_table or filter_table"
    )
    columns: list[str] = Field(
        ..., min_length=1, description="The columns to keep"
    )

class GetKeySchema(BaseModel):
    """ Schema to get a query as a key in the store """

    key: str = Field(
        ..., description="Key of the stored expression, returned by previous operations"
    )

class SortSchema(BaseModel):
    """ Order by a single column"""

    key: str = Field(
        ..., description="Key of the stored expression, returned by previous evaluations"
    )
    column: str = Field(
        ..., min_length=1, description="The field values to sort"
    )
    ascending: bool = Field(
        True, description="if the sort must be ascending"
    )

class LimitSchema(BaseModel):
    """ Order by a single column"""

    key: str = Field(
        ..., description="Key of the stored expression, returned by previous evaluations"
    )
    limit: int = Field(
        ..., ge=1, description="The number of rows to return"
    )