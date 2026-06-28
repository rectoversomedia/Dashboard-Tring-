-- Override dbt schema naming so source-specific models land in their own BQ datasets:
--   moengage_staging, moengage_mart, play_staging, play_mart (verbatim)
-- appsflyer models use dbt default: target.schema + _ + custom_schema_name.
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- elif custom_schema_name.startswith('moengage_') or custom_schema_name.startswith('play_') or custom_schema_name.startswith('appstore_') or custom_schema_name == 'dashboard' -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ default_schema }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
