import json
import math
import urllib
from datasette import hookimpl
from datasette.database import QueryInterrupted
from datasette.utils import (
    escape_sqlite,
    path_with_added_args,
    path_with_removed_args,
    detect_json1,
    sqlite3,
)


def freedman_diaconis_bin_width(values):
    if not values or len(values) < 2:
        return None
    sorted_values = sorted(values)
    n = len(sorted_values)
    q1_index = int(n * 0.25)
    q3_index = int(n * 0.75)
    q1 = sorted_values[q1_index]
    q3 = sorted_values[q3_index]
    iqr = q3 - q1
    if iqr == 0:
        return None
    h = 2 * iqr * (n ** (-1 / 3))
    return h


def round_bin_edges(min_val, max_val, bin_width):
    if bin_width <= 0:
        return min_val, max_val, 1
    if bin_width < 1:
        log10 = math.floor(math.log10(bin_width))
        multiplier = 10**log10
        nice_bin_widths = [1, 2, 5]
        normalized = bin_width / multiplier
        for nice in nice_bin_widths:
            if normalized <= nice:
                bin_width = nice * multiplier
                break
        else:
            bin_width = 10 * multiplier
    else:
        bin_width = math.ceil(bin_width)
    start = math.floor(min_val / bin_width) * bin_width
    end = math.ceil(max_val / bin_width) * bin_width
    if end == start:
        end = start + bin_width
    num_bins = max(1, int(math.ceil((end - start) / bin_width)))
    return start, end, num_bins, bin_width


def calculate_bins(min_val, max_val, values=None, num_unique=None):
    if min_val is None or max_val is None:
        return None
    if min_val == max_val:
        return [(min_val, max_val + 1)]
    if values is not None and len(values) > 0:
        bin_width = freedman_diaconis_bin_width(values)
        if bin_width and bin_width > 0:
            start, end, num_bins, bin_width = round_bin_edges(
                min_val, max_val, bin_width
            )
            bins = []
            for i in range(num_bins):
                bin_start = start + i * bin_width
                bin_end = bin_start + bin_width
                bins.append((bin_start, bin_end))
            return bins
    if num_unique is not None and num_unique <= 10:
        ranges = []
        sorted_unique = sorted(set(values) if values else [])
        for i in range(len(sorted_unique)):
            if i == 0:
                start = sorted_unique[i] - 0.5 if sorted_unique[i] == int(sorted_unique[i]) else sorted_unique[i]
            else:
                start = (sorted_unique[i] + sorted_unique[i-1]) / 2
            if i == len(sorted_unique) - 1:
                end = sorted_unique[i] + 0.5 if sorted_unique[i] == int(sorted_unique[i]) else sorted_unique[i] + 0.1
            else:
                end = (sorted_unique[i] + sorted_unique[i+1]) / 2
            ranges.append((start, end))
        return ranges
    data_range = max_val - min_val
    if data_range <= 0:
        return [(min_val, max_val + 1)]
    sqrt_n = math.sqrt(len(values) if values else 100)
    num_bins = max(5, min(50, int(sqrt_n)))
    bin_width = data_range / num_bins
    start, end, num_bins, bin_width = round_bin_edges(min_val, max_val, bin_width)
    bins = []
    for i in range(num_bins):
        bin_start = start + i * bin_width
        bin_end = bin_start + bin_width
        bins.append((bin_start, bin_end))
    return bins


def load_facet_configs(request, table_config):
    # Given a request and the configuration for a table, return
    # a dictionary of selected facets, their lists of configs and for each
    # config whether it came from the request or the metadata.
    #
    #   return {type: [
    #       {"source": "metadata", "config": config1},
    #       {"source": "request", "config": config2}]}
    facet_configs = {}
    table_config = table_config or {}
    table_facet_configs = table_config.get("facets", [])
    for facet_config in table_facet_configs:
        if isinstance(facet_config, str):
            type = "column"
            facet_config = {"simple": facet_config}
        else:
            assert (
                len(facet_config.values()) == 1
            ), "Metadata config dicts should be {type: config}"
            type, facet_config = list(facet_config.items())[0]
            if isinstance(facet_config, str):
                facet_config = {"simple": facet_config}
        facet_configs.setdefault(type, []).append(
            {"source": "metadata", "config": facet_config}
        )
    qs_pairs = urllib.parse.parse_qs(request.query_string, keep_blank_values=True)
    for key, values in qs_pairs.items():
        if key.startswith("_facet"):
            # Figure out the facet type
            if key == "_facet":
                type = "column"
            elif key.startswith("_facet_"):
                type = key[len("_facet_") :]
            for value in values:
                # The value is the facet_config - either JSON or not
                facet_config = (
                    json.loads(value) if value.startswith("{") else {"simple": value}
                )
                facet_configs.setdefault(type, []).append(
                    {"source": "request", "config": facet_config}
                )
    return facet_configs


@hookimpl
def register_facet_classes():
    classes = [ColumnFacet, DateFacet, HistogramFacet]
    if detect_json1():
        classes.append(ArrayFacet)
    return classes


class Facet:
    type = None
    # How many rows to consider when suggesting facets:
    suggest_consider = 1000

    def __init__(
        self,
        ds,
        request,
        database,
        sql=None,
        table=None,
        params=None,
        table_config=None,
        row_count=None,
    ):
        assert table or sql, "Must provide either table= or sql="
        self.ds = ds
        self.request = request
        self.database = database
        # For foreign key expansion. Can be None for e.g. canned SQL queries:
        self.table = table
        self.sql = sql or f"select * from [{table}]"
        self.params = params or []
        self.table_config = table_config
        # row_count can be None, in which case we calculate it ourselves:
        self.row_count = row_count

    def get_configs(self):
        configs = load_facet_configs(self.request, self.table_config)
        return configs.get(self.type) or []

    def get_querystring_pairs(self):
        # ?_foo=bar&_foo=2&empty= becomes:
        # [('_foo', 'bar'), ('_foo', '2'), ('empty', '')]
        return urllib.parse.parse_qsl(self.request.query_string, keep_blank_values=True)

    def get_facet_size(self):
        facet_size = self.ds.setting("default_facet_size")
        max_returned_rows = self.ds.setting("max_returned_rows")
        table_facet_size = None
        if self.table:
            config_facet_size = (
                self.ds.config.get("databases", {})
                .get(self.database, {})
                .get("tables", {})
                .get(self.table, {})
                .get("facet_size")
            )
            if config_facet_size:
                table_facet_size = config_facet_size
        custom_facet_size = self.request.args.get("_facet_size")
        if custom_facet_size:
            if custom_facet_size == "max":
                facet_size = max_returned_rows
            elif custom_facet_size.isdigit():
                facet_size = int(custom_facet_size)
            else:
                # Invalid value, ignore it
                custom_facet_size = None
        if table_facet_size and not custom_facet_size:
            if table_facet_size == "max":
                facet_size = max_returned_rows
            else:
                facet_size = table_facet_size
        return min(facet_size, max_returned_rows)

    async def suggest(self):
        return []

    async def facet_results(self):
        # returns ([results], [timed_out])
        # TODO: Include "hideable" with each one somehow, which indicates if it was
        # defined in metadata (in which case you cannot turn it off)
        raise NotImplementedError

    async def get_columns(self, sql, params=None):
        # Detect column names using the "limit 0" trick
        return (
            await self.ds.execute(
                self.database, f"select * from ({sql}) limit 0", params or []
            )
        ).columns


class ColumnFacet(Facet):
    type = "column"

    async def suggest(self):
        row_count = await self.get_row_count()
        columns = await self.get_columns(self.sql, self.params)
        facet_size = self.get_facet_size()
        suggested_facets = []
        already_enabled = [c["config"]["simple"] for c in self.get_configs()]
        for column in columns:
            if column in already_enabled:
                continue
            suggested_facet_sql = """
                with limited as (select * from ({sql}) limit {suggest_consider})
                select {column} as value, count(*) as n from limited
                where value is not null
                group by value
                limit {limit}
            """.format(
                column=escape_sqlite(column),
                sql=self.sql,
                limit=facet_size + 1,
                suggest_consider=self.suggest_consider,
            )
            distinct_values = None
            try:
                distinct_values = await self.ds.execute(
                    self.database,
                    suggested_facet_sql,
                    self.params,
                    truncate=False,
                    custom_time_limit=self.ds.setting("facet_suggest_time_limit_ms"),
                )
                num_distinct_values = len(distinct_values)
                if (
                    1 < num_distinct_values < row_count
                    and num_distinct_values <= facet_size
                    # And at least one has n > 1
                    and any(r["n"] > 1 for r in distinct_values)
                ):
                    suggested_facets.append(
                        {
                            "name": column,
                            "toggle_url": self.ds.absolute_url(
                                self.request,
                                self.ds.urls.path(
                                    path_with_added_args(
                                        self.request, {"_facet": column}
                                    )
                                ),
                            ),
                        }
                    )
            except QueryInterrupted:
                continue
        return suggested_facets

    async def get_row_count(self):
        if self.row_count is None:
            self.row_count = (
                await self.ds.execute(
                    self.database,
                    f"select count(*) from (select * from ({self.sql}) limit {self.suggest_consider})",
                    self.params,
                )
            ).rows[0][0]
        return self.row_count

    async def facet_results(self):
        facet_results = []
        facets_timed_out = []

        qs_pairs = self.get_querystring_pairs()

        facet_size = self.get_facet_size()
        for source_and_config in self.get_configs():
            config = source_and_config["config"]
            source = source_and_config["source"]
            column = config.get("column") or config["simple"]
            facet_sql = """
                select {col} as value, count(*) as count from (
                    {sql}
                )
                where {col} is not null
                group by {col} order by count desc, value limit {limit}
            """.format(col=escape_sqlite(column), sql=self.sql, limit=facet_size + 1)
            try:
                facet_rows_results = await self.ds.execute(
                    self.database,
                    facet_sql,
                    self.params,
                    truncate=False,
                    custom_time_limit=self.ds.setting("facet_time_limit_ms"),
                )
                facet_results_values = []
                facet_results.append(
                    {
                        "name": column,
                        "type": self.type,
                        "hideable": source != "metadata",
                        "toggle_url": self.ds.urls.path(
                            path_with_removed_args(self.request, {"_facet": column})
                        ),
                        "results": facet_results_values,
                        "truncated": len(facet_rows_results) > facet_size,
                    }
                )
                facet_rows = facet_rows_results.rows[:facet_size]
                if self.table:
                    # Attempt to expand foreign keys into labels
                    values = [row["value"] for row in facet_rows]
                    expanded = await self.ds.expand_foreign_keys(
                        self.request.actor, self.database, self.table, column, values
                    )
                else:
                    expanded = {}
                for row in facet_rows:
                    column_qs = column
                    if column.startswith("_"):
                        column_qs = "{}__exact".format(column)
                    selected = (column_qs, str(row["value"])) in qs_pairs
                    if selected:
                        toggle_path = path_with_removed_args(
                            self.request, {column_qs: str(row["value"])}
                        )
                    else:
                        toggle_path = path_with_added_args(
                            self.request, {column_qs: row["value"]}
                        )
                    facet_results_values.append(
                        {
                            "value": row["value"],
                            "label": expanded.get((column, row["value"]), row["value"]),
                            "count": row["count"],
                            "toggle_url": self.ds.absolute_url(
                                self.request, self.ds.urls.path(toggle_path)
                            ),
                            "selected": selected,
                        }
                    )
            except QueryInterrupted:
                facets_timed_out.append(column)

        return facet_results, facets_timed_out


class ArrayFacet(Facet):
    type = "array"

    def _is_json_array_of_strings(self, json_string):
        try:
            array = json.loads(json_string)
        except ValueError:
            return False
        for item in array:
            if not isinstance(item, str):
                return False
        return True

    async def suggest(self):
        columns = await self.get_columns(self.sql, self.params)
        suggested_facets = []
        already_enabled = [c["config"]["simple"] for c in self.get_configs()]
        for column in columns:
            if column in already_enabled:
                continue
            # Is every value in this column either null or a JSON array?
            suggested_facet_sql = """
                with limited as (select * from ({sql}) limit {suggest_consider})
                select distinct json_type({column})
                from limited
                where {column} is not null and {column} != ''
            """.format(
                column=escape_sqlite(column),
                sql=self.sql,
                suggest_consider=self.suggest_consider,
            )
            try:
                results = await self.ds.execute(
                    self.database,
                    suggested_facet_sql,
                    self.params,
                    truncate=False,
                    custom_time_limit=self.ds.setting("facet_suggest_time_limit_ms"),
                    log_sql_errors=False,
                )
                types = tuple(r[0] for r in results.rows)
                if types in (("array",), ("array", None)):
                    # Now check that first 100 arrays contain only strings
                    first_100 = [
                        v[0]
                        for v in await self.ds.execute(
                            self.database,
                            (
                                "select {column} from ({sql}) "
                                "where {column} is not null "
                                "and {column} != '' "
                                "and json_array_length({column}) > 0 "
                                "limit 100"
                            ).format(column=escape_sqlite(column), sql=self.sql),
                            self.params,
                            truncate=False,
                            custom_time_limit=self.ds.setting(
                                "facet_suggest_time_limit_ms"
                            ),
                            log_sql_errors=False,
                        )
                    ]
                    if first_100 and all(
                        self._is_json_array_of_strings(r) for r in first_100
                    ):
                        suggested_facets.append(
                            {
                                "name": column,
                                "type": "array",
                                "toggle_url": self.ds.absolute_url(
                                    self.request,
                                    self.ds.urls.path(
                                        path_with_added_args(
                                            self.request, {"_facet_array": column}
                                        )
                                    ),
                                ),
                            }
                        )
            except (QueryInterrupted, sqlite3.OperationalError):
                continue
        return suggested_facets

    async def facet_results(self):
        # self.configs should be a plain list of columns
        facet_results = []
        facets_timed_out = []

        facet_size = self.get_facet_size()
        for source_and_config in self.get_configs():
            config = source_and_config["config"]
            source = source_and_config["source"]
            column = config.get("column") or config["simple"]
            # https://github.com/simonw/datasette/issues/448
            facet_sql = """
                with inner as ({sql}),
                deduped_array_items as (
                    select
                        distinct j.value,
                        inner.*
                    from
                        json_each([inner].{col}) j
                        join inner
                )
                select
                    value as value,
                    count(*) as count
                from
                    deduped_array_items
                group by
                    value
                order by
                    count(*) desc, value limit {limit}
            """.format(
                col=escape_sqlite(column),
                sql=self.sql,
                limit=facet_size + 1,
            )
            try:
                facet_rows_results = await self.ds.execute(
                    self.database,
                    facet_sql,
                    self.params,
                    truncate=False,
                    custom_time_limit=self.ds.setting("facet_time_limit_ms"),
                )
                facet_results_values = []
                facet_results.append(
                    {
                        "name": column,
                        "type": self.type,
                        "results": facet_results_values,
                        "hideable": source != "metadata",
                        "toggle_url": self.ds.urls.path(
                            path_with_removed_args(
                                self.request, {"_facet_array": column}
                            )
                        ),
                        "truncated": len(facet_rows_results) > facet_size,
                    }
                )
                facet_rows = facet_rows_results.rows[:facet_size]
                pairs = self.get_querystring_pairs()
                for row in facet_rows:
                    value = str(row["value"])
                    selected = (f"{column}__arraycontains", value) in pairs
                    if selected:
                        toggle_path = path_with_removed_args(
                            self.request, {f"{column}__arraycontains": value}
                        )
                    else:
                        toggle_path = path_with_added_args(
                            self.request, {f"{column}__arraycontains": value}
                        )
                    facet_results_values.append(
                        {
                            "value": value,
                            "label": value,
                            "count": row["count"],
                            "toggle_url": self.ds.absolute_url(
                                self.request, toggle_path
                            ),
                            "selected": selected,
                        }
                    )
            except QueryInterrupted:
                facets_timed_out.append(column)

        return facet_results, facets_timed_out


class DateFacet(Facet):
    type = "date"

    async def suggest(self):
        columns = await self.get_columns(self.sql, self.params)
        already_enabled = [c["config"]["simple"] for c in self.get_configs()]
        suggested_facets = []
        for column in columns:
            if column in already_enabled:
                continue
            # Does this column contain any dates in the first 100 rows?
            suggested_facet_sql = """
                select date({column}) from (
                    select * from ({sql}) limit 100
                ) where {column} glob "????-??-*"
            """.format(column=escape_sqlite(column), sql=self.sql)
            try:
                results = await self.ds.execute(
                    self.database,
                    suggested_facet_sql,
                    self.params,
                    truncate=False,
                    custom_time_limit=self.ds.setting("facet_suggest_time_limit_ms"),
                    log_sql_errors=False,
                )
                values = tuple(r[0] for r in results.rows)
                if any(values):
                    suggested_facets.append(
                        {
                            "name": column,
                            "type": "date",
                            "toggle_url": self.ds.absolute_url(
                                self.request,
                                self.ds.urls.path(
                                    path_with_added_args(
                                        self.request, {"_facet_date": column}
                                    )
                                ),
                            ),
                        }
                    )
            except (QueryInterrupted, sqlite3.OperationalError):
                continue
        return suggested_facets

    async def facet_results(self):
        facet_results = []
        facets_timed_out = []
        args = dict(self.get_querystring_pairs())
        facet_size = self.get_facet_size()
        for source_and_config in self.get_configs():
            config = source_and_config["config"]
            source = source_and_config["source"]
            column = config.get("column") or config["simple"]
            # TODO: does this query break if inner sql produces value or count columns?
            facet_sql = """
                select date({col}) as value, count(*) as count from (
                    {sql}
                )
                where date({col}) is not null
                group by date({col}) order by count desc, value limit {limit}
            """.format(col=escape_sqlite(column), sql=self.sql, limit=facet_size + 1)
            try:
                facet_rows_results = await self.ds.execute(
                    self.database,
                    facet_sql,
                    self.params,
                    truncate=False,
                    custom_time_limit=self.ds.setting("facet_time_limit_ms"),
                )
                facet_results_values = []
                facet_results.append(
                    {
                        "name": column,
                        "type": self.type,
                        "results": facet_results_values,
                        "hideable": source != "metadata",
                        "toggle_url": path_with_removed_args(
                            self.request, {"_facet_date": column}
                        ),
                        "truncated": len(facet_rows_results) > facet_size,
                    }
                )
                facet_rows = facet_rows_results.rows[:facet_size]
                for row in facet_rows:
                    selected = str(args.get(f"{column}__date")) == str(row["value"])
                    if selected:
                        toggle_path = path_with_removed_args(
                            self.request, {f"{column}__date": str(row["value"])}
                        )
                    else:
                        toggle_path = path_with_added_args(
                            self.request, {f"{column}__date": row["value"]}
                        )
                    facet_results_values.append(
                        {
                            "value": row["value"],
                            "label": row["value"],
                            "count": row["count"],
                            "toggle_url": self.ds.absolute_url(
                                self.request, toggle_path
                            ),
                            "selected": selected,
                        }
                    )
            except QueryInterrupted:
                facets_timed_out.append(column)

        return facet_results, facets_timed_out


class HistogramFacet(Facet):
    type = "histogram"

    async def suggest(self):
        columns = await self.get_columns(self.sql, self.params)
        already_enabled = [c["config"]["simple"] for c in self.get_configs()]
        suggested_facets = []
        for column in columns:
            if column in already_enabled:
                continue
            try:
                stats_sql = """
                    with limited as (select * from ({sql}) limit {suggest_consider})
                    select
                        min({column}) as min_val,
                        max({column}) as max_val,
                        count(distinct {column}) as distinct_count,
                        count({column}) as non_null_count
                    from limited
                    where {column} is not null
                """.format(
                    column=escape_sqlite(column),
                    sql=self.sql,
                    suggest_consider=self.suggest_consider,
                )
                stats = await self.ds.execute(
                    self.database,
                    stats_sql,
                    self.params,
                    truncate=False,
                    custom_time_limit=self.ds.setting("facet_suggest_time_limit_ms"),
                    log_sql_errors=False,
                )
                if not stats.rows:
                    continue
                row = stats.rows[0]
                min_val = row["min_val"]
                max_val = row["max_val"]
                distinct_count = row["distinct_count"]
                non_null_count = row["non_null_count"]

                if non_null_count < 2:
                    continue
                if min_val is None or max_val is None:
                    continue

                if not isinstance(min_val, (int, float)) or not isinstance(max_val, (int, float)):
                    continue

                value_range = max_val - min_val
                if value_range <= 0:
                    continue

                if distinct_count == non_null_count and value_range == distinct_count - 1:
                    continue

                suggested_facets.append(
                    {
                        "name": column,
                        "type": "histogram",
                        "toggle_url": self.ds.absolute_url(
                            self.request,
                            self.ds.urls.path(
                                path_with_added_args(
                                    self.request, {"_facet_histogram": column}
                                )
                            ),
                        ),
                    }
                )
            except (QueryInterrupted, sqlite3.OperationalError):
                continue
        return suggested_facets

    async def facet_results(self):
        facet_results = []
        facets_timed_out = []
        args = dict(self.get_querystring_pairs())
        facet_size = self.get_facet_size()

        for source_and_config in self.get_configs():
            config = source_and_config["config"]
            source = source_and_config["source"]
            column = config.get("column") or config["simple"]

            try:
                stats_sql = """
                    select
                        min({col}) as min_val,
                        max({col}) as max_val,
                        count({col}) as non_null_count,
                        count(*) as total_count
                    from (
                        {sql}
                    )
                """.format(col=escape_sqlite(column), sql=self.sql)
                stats_results = await self.ds.execute(
                    self.database,
                    stats_sql,
                    self.params,
                    truncate=False,
                    custom_time_limit=self.ds.setting("facet_time_limit_ms"),
                )
                stats = stats_results.rows[0]
                min_val = stats["min_val"]
                max_val = stats["max_val"]
                non_null_count = stats["non_null_count"]
                total_count = stats["total_count"]
                null_count = total_count - non_null_count

                if min_val is None or max_val is None:
                    if null_count > 0:
                        facet_results.append(
                            {
                                "name": column,
                                "type": self.type,
                                "results": [],
                                "hideable": source != "metadata",
                                "toggle_url": path_with_removed_args(
                                    self.request, {"_facet_histogram": column}
                                ),
                                "truncated": False,
                                "null_count": null_count,
                            }
                        )
                    continue

                sample_sql = """
                    select {col} as value
                    from (
                        {sql}
                    )
                    where {col} is not null
                    order by random()
                    limit {sample_size}
                """.format(
                    col=escape_sqlite(column),
                    sql=self.sql,
                    sample_size=min(10000, facet_size * 10),
                )
                sample_results = await self.ds.execute(
                    self.database,
                    sample_sql,
                    self.params,
                    truncate=False,
                    custom_time_limit=self.ds.setting("facet_time_limit_ms"),
                )
                sample_values = [
                    row["value"] for row in sample_results.rows if row["value"] is not None
                ]

                bins = calculate_bins(min_val, max_val, sample_values)

                if bins is None:
                    continue

                facet_results_values = []
                max_bin_count = 0

                for bin_start, bin_end in bins:
                    if bin_start == bin_end:
                        bin_end = bin_start + 1

                    bin_sql = """
                        select count(*) as count
                        from (
                            {sql}
                        )
                        where {col} >= ? and {col} < ?
                    """.format(col=escape_sqlite(column), sql=self.sql)

                    bin_params = list(self.params) if self.params else []
                    bin_params.extend([bin_start, bin_end])

                    bin_results = await self.ds.execute(
                        self.database,
                        bin_sql,
                        bin_params,
                        truncate=False,
                        custom_time_limit=self.ds.setting("facet_time_limit_ms"),
                    )
                    bin_count = bin_results.rows[0]["count"] if bin_results.rows else 0
                    max_bin_count = max(max_bin_count, bin_count)

                    gte_key = f"{column}__gte"
                    lt_key = f"{column}__lt"

                    param_gte = args.get(gte_key)
                    param_lt = args.get(lt_key)

                    is_selected = False
                    if param_gte is not None or param_lt is not None:
                        try:
                            param_gte_val = float(param_gte) if param_gte is not None else None
                            param_lt_val = float(param_lt) if param_lt is not None else None
                            gte_overlaps = (param_gte_val is None) or (param_gte_val < bin_end)
                            lt_overlaps = (param_lt_val is None) or (bin_start < param_lt_val)
                            is_selected = gte_overlaps and lt_overlaps
                        except (ValueError, TypeError):
                            is_selected = False

                    if is_selected:
                        toggle_path = path_with_removed_args(
                            self.request, {gte_key, lt_key}
                        )
                    else:
                        path_without_old = path_with_removed_args(
                            self.request, {gte_key, lt_key}
                        )
                        toggle_path = path_with_added_args(
                            self.request,
                            {gte_key: bin_start, lt_key: bin_end},
                            path=path_without_old,
                        )

                    if bin_start == int(bin_start) and bin_end == int(bin_end):
                        label = f"{int(bin_start)} - {int(bin_end)}"
                    else:
                        label = f"{bin_start} - {bin_end}"

                    facet_results_values.append(
                        {
                            "value": {"start": bin_start, "end": bin_end},
                            "label": label,
                            "count": bin_count,
                            "toggle_url": self.ds.absolute_url(self.request, toggle_path),
                            "selected": is_selected,
                            "bin_start": bin_start,
                            "bin_end": bin_end,
                        }
                    )

                facet_results.append(
                    {
                        "name": column,
                        "type": self.type,
                        "results": facet_results_values,
                        "hideable": source != "metadata",
                        "toggle_url": path_with_removed_args(
                            self.request, {"_facet_histogram": column}
                        ),
                        "truncated": False,
                        "null_count": null_count,
                        "min_val": min_val,
                        "max_val": max_val,
                        "max_bin_count": max_bin_count,
                    }
                )

            except QueryInterrupted:
                facets_timed_out.append(column)

        return facet_results, facets_timed_out
