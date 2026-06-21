-- Override dbt schema naming so moengage models land in moengage_staging/moengage_mart
-- while appsflyer models keep their appsflyer_staging/appsflyer_mart datasets.
-- When custom_schema_name starts with a full dataset name (moengage_*), use it verbatim.
-- Otherwise use dbt default: target.schema + _ + custom_schema_name.
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- elif custom_schema_name.startswith('moengage_') -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ default_schema }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
