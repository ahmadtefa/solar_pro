import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/config/app_config.dart';
import '../../core/l10n/app_strings.dart';
import '../../core/models/auth_models.dart';
import '../../core/models/paged_result.dart';
import '../../core/providers.dart';
import '../../core/repository/kayan_api.dart';
import '../../core/utils/formatters.dart';
import '../widgets/async_view.dart';
import '../widgets/dialogs.dart';
import '../widgets/form_fields.dart';
import '../widgets/notify.dart';
import '../widgets/page_header.dart';
import '../widgets/pagination_bar.dart';
import '../widgets/status_chip.dart';
import 'resource_config.dart';
import 'resource_providers.dart';

/// Generic, permission-aware CRUD screen driven by a [ResourceConfig].
///
/// One widget covers every master-data list in the ERP: search, filters,
/// sorting, pagination, create/edit forms, delete confirmation and export. The
/// server still owns validation, uniqueness and authorisation.
class ResourcePage extends ConsumerStatefulWidget {
  const ResourcePage({required this.config, this.headerActions = const <Widget>[], super.key});

  final ResourceConfig config;
  final List<Widget> headerActions;

  @override
  ConsumerState<ResourcePage> createState() => _ResourcePageState();
}

class _ResourcePageState extends ConsumerState<ResourcePage> {
  late ListQuery _query = ListQuery(
    path: widget.config.path,
    pageSize: AppConfig.defaultPageSize,
    sortBy: widget.config.defaultSortBy,
    sortDir: widget.config.defaultSortDir,
    filters: widget.config.buildFilters(const <String, dynamic>{}),
  );
  final Map<String, dynamic> _activeFilters = <String, dynamic>{};
  final TextEditingController _searchController = TextEditingController();
  Timer? _debounce;

  ResourceConfig get config => widget.config;

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  void _reload() => ref.invalidate(listQueryProvider(_query));

  void _onSearchChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      if (!mounted) return;
      setState(() {
        _query = value.trim().isEmpty
            ? _query.copyWith(page: 1, clearQ: true)
            : _query.copyWith(page: 1, q: value.trim());
      });
    });
  }

  void _applyFilters(Map<String, dynamic> filters) {
    setState(() {
      _activeFilters
        ..clear()
        ..addAll(filters);
      _query = _query.copyWith(page: 1, filters: config.buildFilters(filters));
    });
  }

  Future<void> _openForm({Map<String, dynamic>? record}) async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => ResourceFormDialog(config: config, record: record),
    );
    if (saved == true && mounted) {
      _reload();
      context.showSuccess(record == null ? 'resource.created' : 'resource.updated');
    }
  }

  Future<void> _delete(Map<String, dynamic> record) async {
    if (!await confirmDialog(context)) return;
    try {
      await ref.read(apiProvider).remove(config.path, '${record['id']}');
      if (mounted) {
        _reload();
        context.showSuccess('resource.deleted');
      }
    } catch (error) {
      if (mounted) context.showError(error);
    }
  }

  Future<void> _export() async {
    final String? entity = config.exportEntity;
    if (entity == null) return;
    try {
      final KayanApi api = ref.read(apiProvider);
      final DownloadTicket ticket = await api.downloadTicket(kind: 'entity', code: entity, fileFormat: 'csv');
      await _open(ticket.url);
    } catch (error) {
      if (mounted) context.showError(error);
    }
  }

  Future<void> _open(String url) async {
    final Uri? uri = Uri.tryParse(url);
    if (uri == null) return;
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  @override
  Widget build(BuildContext context) {
    final AuthState auth = ref.watch(authProvider);
    final bool canCreate = config.canCreate && auth.can(config.createPermission);
    final AsyncValue<PagedResult<Map<String, dynamic>>> list = ref.watch(listQueryProvider(_query));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        PageHeader(
          titleKey: config.nameKey,
          breadcrumbs: config.breadcrumbs,
          actions: <Widget>[
            ...widget.headerActions,
            if (config.canExport && config.exportEntity != null)
              OutlinedButton.icon(
                onPressed: _export,
                icon: const Icon(Icons.file_download_outlined, size: 18),
                label: Text(context.tr('common.export')),
              ),
            IconButton(
              tooltip: context.tr('common.refresh'),
              onPressed: _reload,
              icon: const Icon(Icons.refresh),
            ),
            if (canCreate)
              FilledButton.icon(
                onPressed: config.readOnly ? null : () => _openForm(),
                icon: const Icon(Icons.add, size: 18),
                label: Text(context.tr('common.new')),
              ),
          ],
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: _FilterBar(
            config: config,
            searchController: _searchController,
            filters: _activeFilters,
            onSearchChanged: _onSearchChanged,
            onFiltersChanged: _applyFilters,
          ),
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
            child: AsyncView<PagedResult<Map<String, dynamic>>>(
              value: list,
              onRetry: _reload,
              isEmpty: (PagedResult<Map<String, dynamic>> data) => data.items.isEmpty,
              builder: (PagedResult<Map<String, dynamic>> data) => Column(
                children: <Widget>[
                  Expanded(
                    child: DataTableView(
                      columns: config.columns,
                      rows: data.items,
                      onSort: (String key, bool ascending) => setState(
                        () => _query = _query.copyWith(sortBy: key, sortDir: ascending ? 'asc' : 'desc'),
                      ),
                      sortBy: _query.sortBy,
                      sortDir: _query.sortDir,
                      actions: (Map<String, dynamic> row) => <Widget>[
                        if (config.canEdit && auth.can(config.editPermission))
                          IconButton(
                            tooltip: context.tr('common.edit'),
                            icon: const Icon(Icons.edit_outlined, size: 18),
                            onPressed: config.readOnly ? null : () => _openForm(record: row),
                          ),
                        if (config.canDelete && auth.can(config.deletePermission))
                          IconButton(
                            tooltip: context.tr('common.delete'),
                            icon: const Icon(Icons.delete_outline, size: 18),
                            onPressed: () => _delete(row),
                          ),
                      ],
                    ),
                  ),
                  PaginationBar(
                    page: data.page,
                    pages: data.pages,
                    total: data.total,
                    pageSize: data.pageSize,
                    onPageChanged: (int page) => setState(() => _query = _query.copyWith(page: page)),
                    onPageSizeChanged: (int size) =>
                        setState(() => _query = _query.copyWith(page: 1, pageSize: size)),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _FilterBar extends ConsumerWidget {
  const _FilterBar({
    required this.config,
    required this.searchController,
    required this.filters,
    required this.onSearchChanged,
    required this.onFiltersChanged,
  });

  final ResourceConfig config;
  final TextEditingController searchController;
  final Map<String, dynamic> filters;
  final ValueChanged<String> onSearchChanged;
  final ValueChanged<Map<String, dynamic>> onFiltersChanged;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Wrap(
      spacing: 10,
      runSpacing: 8,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: <Widget>[
        if (config.searchable)
          SizedBox(
            width: 300,
            child: TextField(
              controller: searchController,
              onChanged: onSearchChanged,
              decoration: InputDecoration(
                hintText: context.tr('common.search_hint'),
                prefixIcon: const Icon(Icons.search, size: 18),
                suffixIcon: searchController.text.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.close, size: 16),
                        onPressed: () {
                          searchController.clear();
                          onSearchChanged('');
                        },
                      ),
              ),
            ),
          ),
        for (final FilterSpec filter in config.filters) _FilterField(filter: filter, filters: filters, onChanged: onFiltersChanged),
        if (filters.isNotEmpty)
          TextButton.icon(
            onPressed: () => onFiltersChanged(<String, dynamic>{}),
            icon: const Icon(Icons.filter_alt_off_outlined, size: 16),
            label: Text(context.tr('common.reset')),
          ),
      ],
    );
  }
}

class _FilterField extends ConsumerWidget {
  const _FilterField({required this.filter, required this.filters, required this.onChanged});

  final FilterSpec filter;
  final Map<String, dynamic> filters;
  final ValueChanged<Map<String, dynamic>> onChanged;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final String? current = filters[filter.key]?.toString();

    if (filter.type == FieldType.date) {
      return SizedBox(
        width: 170,
        child: TextField(
          readOnly: true,
          controller: TextEditingController(text: current == null ? '' : Fmt.isoDate(current)),
          decoration: InputDecoration(
            labelText: context.tr(filter.labelKey),
            suffixIcon: IconButton(
              icon: const Icon(Icons.calendar_today, size: 14),
              onPressed: () async {
                final DateTime? picked = await showDatePicker(
                  context: context,
                  initialDate: Fmt.toDate(current) ?? DateTime.now(),
                  firstDate: DateTime(2000),
                  lastDate: DateTime(2100),
                );
                if (picked != null) {
                  onChanged(<String, dynamic>{...filters, filter.key: Fmt.isoDate(picked)});
                }
              },
            ),
            suffix: current == null
                ? null
                : IconButton(
                    icon: const Icon(Icons.close, size: 14),
                    onPressed: () {
                      final Map<String, dynamic> next = Map<String, dynamic>.from(filters)..remove(filter.key);
                      onChanged(next);
                    },
                  ),
          ),
        ),
      );
    }

    final List<DropdownOption> staticOptions = filter.options ?? const <DropdownOption>[];
    if (filter.optionsKey == null) {
      return SizedBox(
        width: 200,
        child: DropdownButtonFormField<String>(
          value: current,
          isExpanded: true,
          decoration: InputDecoration(labelText: context.tr(filter.labelKey)),
          items: <DropdownMenuItem<String>>[
            DropdownMenuItem<String>(value: '', child: Text(context.tr('common.all'))),
            for (final DropdownOption option in staticOptions)
              DropdownMenuItem<String>(
                value: option.value,
                child: Text(option.label.startsWith('label.') ? context.tr(option.label) : option.label),
              ),
          ],
          onChanged: (String? value) {
            final Map<String, dynamic> next = Map<String, dynamic>.from(filters);
            if (value == null || value.isEmpty) {
              next.remove(filter.key);
            } else {
              next[filter.key] = value;
            }
            onChanged(next);
          },
        ),
      );
    }

    return SizedBox(
      width: 220,
      child: ref.watch(optionsProvider(filter.optionsKey!)).when(
            data: (List<LookupOption> options) => DropdownButtonFormField<String>(
              value: current,
              isExpanded: true,
              decoration: InputDecoration(labelText: context.tr(filter.labelKey)),
              items: <DropdownMenuItem<String>>[
                DropdownMenuItem<String>(value: '', child: Text(context.tr('common.all'))),
                for (final LookupOption option in options)
                  DropdownMenuItem<String>(
                    value: option.id,
                    child: Text(option.label, overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: (String? value) {
                final Map<String, dynamic> next = Map<String, dynamic>.from(filters);
                if (value == null || value.isEmpty) {
                  next.remove(filter.key);
                } else {
                  next[filter.key] = value;
                }
                onChanged(next);
              },
            ),
            loading: () => const InputDecorator(
              decoration: InputDecoration(labelText: '...'),
              child: SizedBox(height: 18, child: Center(child: LinearProgressIndicator())),
            ),
            error: (Object error, StackTrace stack) => InputDecorator(
              decoration: InputDecoration(labelText: context.tr(filter.labelKey), errorText: '!'),
              child: const SizedBox(height: 18),
            ),
          ),
    );
  }
}

/// Material table bound to [ColumnSpec]s, with optional row actions.
class DataTableView extends StatelessWidget {
  const DataTableView({
    required this.columns,
    required this.rows,
    this.onRowTap,
    this.actions,
    this.onSort,
    this.sortBy,
    this.sortDir = 'asc',
    this.currencyCode,
    this.emptyKey = 'common.no_data',
    super.key,
  });

  final List<ColumnSpec> columns;
  final List<Map<String, dynamic>> rows;
  final void Function(Map<String, dynamic> row)? onRowTap;
  final List<Widget> Function(Map<String, dynamic> row)? actions;
  final void Function(String key, bool ascending)? onSort;
  final String? sortBy;
  final String sortDir;
  final String? currencyCode;
  final String emptyKey;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String locale = Localizations.localeOf(context).languageCode;
    if (rows.isEmpty) return EmptyState(messageKey: emptyKey);

    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        return Scrollbar(
          child: SingleChildScrollView(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: ConstrainedBox(
                constraints: BoxConstraints(minWidth: constraints.maxWidth),
                child: DataTable(
                  sortColumnIndex: sortBy == null
                      ? null
                      : columns.indexWhere((ColumnSpec column) => column.key == sortBy).clamp(0, columns.length - 1),
                  sortAscending: sortDir != 'desc',
                  showCheckboxColumn: false,
                  columns: <DataColumn>[
                    for (final ColumnSpec column in columns)
                      DataColumn(
                        label: SizedBox(
                          width: column.width,
                          child: Text(context.tr(column.labelKey), textAlign: column.textAlign),
                        ),
                        onSort: onSort == null || !column.sortable
                            ? null
                            : (int index, bool ascending) => onSort!(column.key, ascending),
                      ),
                    if (actions != null) DataColumn(label: Text(context.tr('common.actions'))),
                  ],
                  rows: <DataRow>[
                    for (final Map<String, dynamic> row in rows)
                      DataRow(
                        onSelectChanged: onRowTap == null ? null : (bool? _) => onRowTap!(row),
                        cells: <DataCell>[
                          for (final ColumnSpec column in columns)
                            DataCell(
                              SizedBox(
                                width: column.width,
                                child: Align(
                                  alignment: switch (column.align) {
                                    MainAxisAlignment.center => Alignment.center,
                                    MainAxisAlignment.end => Alignment.centerRight,
                                    _ => Alignment.centerLeft,
                                  },
                                  child: _cell(context, column, row, locale),
                                ),
                              ),
                            ),
                          if (actions != null) DataCell(Row(mainAxisSize: MainAxisSize.min, children: actions!(row))),
                        ],
                      ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _cell(BuildContext context, ColumnSpec column, Map<String, dynamic> row, String locale) {
    final Object? value = row[column.key];
    if (column.isStatus) return StatusChip(value, compact: true);
    final TextStyle? style = column.emphasize
        ? Theme.of(context).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600)
        : null;
    switch (column.type) {
      case FieldType.decimal:
        return Text(Fmt.money(value, locale: locale, currency: column.currency ?? currencyCode), style: style);
      case FieldType.integer:
        return Text(Fmt.quantity(value, locale: locale), style: style);
      case FieldType.date:
        return Text(Fmt.date(value, locale: locale), style: style);
      case FieldType.dateTime:
        return Text(Fmt.dateTime(value, locale: locale), style: style);
      case FieldType.boolean:
        return Icon(
          Fmt.toBool(value) ? Icons.check_circle_outline : Icons.remove_circle_outline,
          size: 16,
          color: Fmt.toBool(value) ? Colors.green.shade600 : Theme.of(context).colorScheme.outline,
        );
      default:
        return Text(
          value == null || '$value'.isEmpty ? context.tr('common.empty_value') : '$value',
          style: style,
          overflow: TextOverflow.ellipsis,
          maxLines: 1,
        );
    }
  }
}

/// Create/edit dialog for a [ResourceConfig].
class ResourceFormDialog extends ConsumerStatefulWidget {
  const ResourceFormDialog({required this.config, this.record, super.key});

  final ResourceConfig config;
  final Map<String, dynamic>? record;

  @override
  ConsumerState<ResourceFormDialog> createState() => _ResourceFormDialogState();
}

class _ResourceFormDialogState extends ConsumerState<ResourceFormDialog> {
  final Map<String, dynamic> _values = <String, dynamic>{};
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _values.addAll(widget.config.defaultValues);
    final Map<String, dynamic>? record = widget.record;
    if (record != null) {
      for (final FieldSpec field in widget.config.fields) {
        if (record[field.key] != null) _values[field.key] = record[field.key];
      }
    }
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _saving = true);
    try {
      final KayanApi api = ref.read(apiProvider);
      final Map<String, dynamic> payload = <String, dynamic>{
        for (final MapEntry<String, dynamic> entry in _values.entries) entry.key: entry.value,
      };
      if (widget.record == null) {
        await api.create(widget.config.path, payload);
      } else {
        await api.update(widget.config.path, '${widget.record!['id']}', payload);
      }
      if (mounted) Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) {
        setState(() => _saving = false);
        context.showError(error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final bool editing = widget.record != null;
    return AlertDialog(
      title: Text(context.tr(editing ? 'resource.edit' : 'resource.new')),
      content: SizedBox(
        width: widget.config.formWidth,
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            child: Wrap(
              crossAxisAlignment: WrapCrossAlignment.start,
              children: <Widget>[
                for (final FieldSpec field in widget.config.fields)
                  SpecField(
                    key: ValueKey<String>('${field.key}-${widget.record?['id']}'),
                    spec: field,
                    onChanged: (Object? value) {
                      if (value == null) {
                        _values.remove(field.key);
                      } else {
                        _values[field.key] = value;
                      }
                    },
                  ),
              ],
            ),
          ),
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(false),
          child: Text(context.tr('common.cancel')),
        ),
        FilledButton.icon(
          onPressed: _saving ? null : _save,
          icon: _saving
              ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.save_outlined, size: 18),
          label: Text(context.tr('common.save')),
        ),
      ],
    );
  }
}
