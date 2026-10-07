import 'package:flutter/material.dart';

/// Field/column value types understood by the generic resource engine.
enum FieldType { text, multiline, integer, decimal, date, dateTime, boolean, select, reference, hidden }

/// Declarative description of one editable form field.
///
/// Fields never contain business rules: they describe *how* to collect a value.
/// The server validates everything again (permissions, uniqueness, ranges).
class FieldSpec {
  const FieldSpec({
    required this.key,
    required this.labelKey,
    this.type = FieldType.text,
    this.required = false,
    this.optionsKey,
    this.options,
    this.helpKey,
    this.defaultValue,
    this.readOnly = false,
    this.span = 1,
    this.minLines = 1,
    this.maxLines = 3,
    this.icon,
  });

  final String key;
  final String labelKey;
  final FieldType type;
  final bool required;

  /// `lookup:<name>` or `list:<path>#<label field>` — resolved by `optionsProvider`.
  final String? optionsKey;
  final List<DropdownOption>? options;
  final String? helpKey;
  final Object? defaultValue;
  final bool readOnly;
  final int span;
  final int minLines;
  final int maxLines;
  final IconData? icon;
}

class DropdownOption {
  const DropdownOption(this.value, this.labelKey);

  final String value;
  final String labelKey;
}

/// One column of a data table.
class ColumnSpec {
  const ColumnSpec(
    this.key,
    this.labelKey, {
    this.type = FieldType.text,
    this.width,
    this.align = MainAxisAlignment.start,
    this.isStatus = false,
    this.currency,
    this.emphasize = false,
    this.sortable = true,
  });

  final String key;
  final String labelKey;
  final FieldType type;
  final double? width;
  final MainAxisAlignment align;
  final bool isStatus;
  final String? currency;
  final bool emphasize;
  final bool sortable;

  TextAlign get textAlign => switch (align) {
        MainAxisAlignment.center => TextAlign.center,
        MainAxisAlignment.end => TextAlign.end,
        _ => TextAlign.start,
      };
}

/// One filter offered above a table.
class FilterSpec {
  const FilterSpec({
    required this.key,
    required this.labelKey,
    this.type = FieldType.select,
    this.optionsKey,
    this.options,
    this.queryParam,
  });

  final String key;
  final String labelKey;
  final FieldType type;
  final String? optionsKey;
  final List<DropdownOption>? options;

  /// Overrides the query parameter name sent to the API.
  final String? queryParam;

  String get parameter => queryParam ?? key;
}

/// Everything the generic CRUD page needs to render and mutate a resource.
class ResourceConfig {
  const ResourceConfig({
    required this.nameKey,
    required this.path,
    required this.permissionPrefix,
    required this.columns,
    this.fields = const <FieldSpec>[],
    this.filters = const <FilterSpec>[],
    this.nameField = 'name',
    this.searchable = true,
    this.canCreate = true,
    this.canEdit = true,
    this.canDelete = true,
    this.canExport = true,
    this.readOnly = false,
    this.defaultSortBy,
    this.defaultSortDir = 'desc',
    this.staticFilters = const <String, Object?>{},
    this.defaultValues = const <String, Object?>{},
    this.breadcrumbs = const <String>[],
    this.icon,
    this.rowQuery,
    this.detailPath,
    this.exportEntity,
    this.formWidth = 680,
  });

  final String nameKey;
  final String path;
  final String permissionPrefix;
  final List<ColumnSpec> columns;
  final List<FieldSpec> fields;
  final List<FilterSpec> filters;
  final String nameField;
  final bool searchable;
  final bool canCreate;
  final bool canEdit;
  final bool canDelete;
  final bool canExport;
  final bool readOnly;
  final String? defaultSortBy;
  final String defaultSortDir;

  /// Filters always applied (for example `warehouse_id` of the active context).
  final Map<String, Object?> staticFilters;
  final Map<String, Object?> defaultValues;
  final List<String> breadcrumbs;
  final IconData? icon;

  /// Extra query parameters merged into every list request.
  final Map<String, Object?>? rowQuery;

  /// Where to open a row when a bespoke detail page exists.
  final String? detailPath;

  /// Entity key accepted by the import/export engine, when exporting is possible.
  final String? exportEntity;
  final double formWidth;

  String get viewPermission => '$permissionPrefix.view';
  String get createPermission => '$permissionPrefix.create';
  String get editPermission => '$permissionPrefix.edit';
  String get deletePermission => '$permissionPrefix.delete';

  Map<String, dynamic> buildFilters(Map<String, dynamic> userFilters) => <String, dynamic>{
        ...staticFilters,
        ...userFilters,
      };
}

/// Identity of a paged list request, used as a provider family key.
class ListQuery {
  const ListQuery({
    required this.path,
    this.page = 1,
    this.pageSize = 25,
    this.q,
    this.sortBy,
    this.sortDir = 'desc',
    this.filters = const <String, dynamic>{},
  });

  final String path;
  final int page;
  final int pageSize;
  final String? q;
  final String? sortBy;
  final String sortDir;
  final Map<String, dynamic> filters;

  ListQuery copyWith({
    String? path,
    int? page,
    int? pageSize,
    String? q,
    bool clearQ = false,
    String? sortBy,
    String? sortDir,
    Map<String, dynamic>? filters,
  }) {
    return ListQuery(
      path: path ?? this.path,
      page: page ?? this.page,
      pageSize: pageSize ?? this.pageSize,
      q: clearQ ? null : (q ?? this.q),
      sortBy: sortBy ?? this.sortBy,
      sortDir: sortDir ?? this.sortDir,
      filters: filters ?? this.filters,
    );
  }

  @override
  bool operator ==(Object other) {
    if (other is! ListQuery) return false;
    return other.path == path &&
        other.page == page &&
        other.pageSize == pageSize &&
        other.q == q &&
        other.sortBy == sortBy &&
        other.sortDir == sortDir &&
        _sameFilters(other.filters, filters);
  }

  @override
  int get hashCode => Object.hash(path, page, pageSize, q, sortBy, sortDir, filters.length);

  static bool _sameFilters(Map<String, dynamic> left, Map<String, dynamic> right) {
    if (left.length != right.length) return false;
    for (final MapEntry<String, dynamic> entry in left.entries) {
      if ('${right[entry.key]}' != '${entry.value}') return false;
    }
    return true;
  }
}

/// Identity of a single record request.
class RecordRef {
  const RecordRef(this.path, this.id);

  final String path;
  final String id;

  @override
  bool operator ==(Object other) => other is RecordRef && other.path == path && other.id == id;

  @override
  int get hashCode => Object.hash(path, id);
}
