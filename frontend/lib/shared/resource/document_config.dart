import 'package:flutter/material.dart';

import 'resource_config.dart';

/// One lifecycle button shown on the document detail panel.
class DocumentActionSpec {
  const DocumentActionSpec({
    required this.endpoint,
    required this.labelKey,
    this.permissionAction,
    this.icon,
    this.needsReason = false,
    this.body = const <String, dynamic>{},
    this.confirmKey,
    this.destructive = false,
    this.visibleWhen = const <String>[],
  });

  /// Path segment appended to the document URL (`submit`, `post`, `unpost`...).
  final String endpoint;
  final String labelKey;

  /// Permission action used for the check; defaults to the endpoint name.
  final String? permissionAction;
  final IconData? icon;
  final bool needsReason;
  final Map<String, dynamic> body;
  final String? confirmKey;
  final bool destructive;

  /// Document statuses the action is offered for. Empty means "always".
  final List<String> visibleWhen;

  String permission(String prefix) => '$prefix.${permissionAction ?? endpoint}';

  bool isVisibleFor(String? status) {
    if (visibleWhen.isEmpty) return true;
    return visibleWhen.contains('${status ?? ''}');
  }
}

/// Everything the generic document screen needs for one document type.
class DocumentConfig {
  const DocumentConfig({
    required this.nameKey,
    required this.singularKey,
    required this.path,
    required this.permissionPrefix,
    required this.columns,
    required this.headerFields,
    this.lineFields = const <FieldSpec>[],
    this.filters = const <FilterSpec>[],
    this.statuses = const <String>['draft', 'submitted', 'approved', 'posted', 'cancelled'],
    this.linesPath = 'lines',
    this.partyFilterKey = 'party_id',
    this.canCreate = true,
    this.totals = const <String>['subtotal', 'discount_amount', 'tax_amount', 'total_amount'],
    this.extraActions = const <DocumentActionSpec>[],
    this.breadcrumbs = const <String>[],
    this.dateField = 'document_date',
    this.currencyField = 'currency_code',
    this.icon,
  });

  final String nameKey;
  final String singularKey;
  final String path;
  final String permissionPrefix;
  final List<ColumnSpec> columns;
  final List<FieldSpec> headerFields;
  final List<FieldSpec> lineFields;
  final List<FilterSpec> filters;
  final List<String> statuses;
  final String linesPath;
  final String partyFilterKey;
  final bool canCreate;

  /// Header fields displayed as money on the detail panel.
  final List<String> totals;
  final List<DocumentActionSpec> extraActions;
  final List<String> breadcrumbs;
  final String dateField;
  final String currencyField;
  final IconData? icon;

  String get viewPermission => '$permissionPrefix.view';
  String get createPermission => '$permissionPrefix.create';
  String get editPermission => '$permissionPrefix.edit';
  String get deletePermission => '$permissionPrefix.delete';
  String get postPermission => '$permissionPrefix.post';
  String get unpostPermission => '$permissionPrefix.unpost';
  String get approvePermission => '$permissionPrefix.approve';
  String get rejectPermission => '$permissionPrefix.reject';
  String get cancelPermission => '$permissionPrefix.cancel';
  String get printPermission => '$permissionPrefix.print';

  /// The lifecycle buttons offered on every document, filtered by status.
  static const List<DocumentActionSpec> standardActions = <DocumentActionSpec>[
    DocumentActionSpec(
      endpoint: 'submit',
      labelKey: 'action.submit',
      permissionAction: 'edit',
      icon: Icons.send_outlined,
      visibleWhen: <String>['draft', 'rejected'],
    ),
    DocumentActionSpec(
      endpoint: 'approve',
      labelKey: 'action.approve',
      icon: Icons.verified_outlined,
      visibleWhen: <String>['draft', 'submitted'],
    ),
    DocumentActionSpec(
      endpoint: 'reject',
      labelKey: 'action.reject',
      icon: Icons.block_outlined,
      needsReason: true,
      destructive: true,
      visibleWhen: <String>['submitted', 'draft'],
    ),
    DocumentActionSpec(
      endpoint: 'post',
      labelKey: 'action.post',
      icon: Icons.post_add_outlined,
      visibleWhen: <String>['draft', 'approved', 'partially_fulfilled'],
    ),
    DocumentActionSpec(
      endpoint: 'unpost',
      labelKey: 'action.unpost',
      icon: Icons.undo_outlined,
      needsReason: true,
      destructive: true,
      visibleWhen: <String>['posted'],
    ),
    DocumentActionSpec(
      endpoint: 'cancel',
      labelKey: 'action.cancel',
      icon: Icons.cancel_outlined,
      needsReason: true,
      destructive: true,
      visibleWhen: <String>['draft', 'submitted', 'approved', 'posted'],
    ),
  ];
}
