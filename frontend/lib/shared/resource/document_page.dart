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
import 'document_config.dart';
import 'resource_config.dart';
import 'resource_page.dart' show DataTableView;
import 'resource_providers.dart';

/// Generic lifecycle screen for a document type (quotation, order, invoice...).
///
/// List with filters, detail panel with lines and totals, permission-checked
/// lifecycle actions, audit timeline and printing.
class DocumentPage extends ConsumerStatefulWidget {
  const DocumentPage({required this.config, this.headerActions = const <Widget>[], super.key});

  final DocumentConfig config;
  final List<Widget> headerActions;

  @override
  ConsumerState<DocumentPage> createState() => _DocumentPageState();
}

class _DocumentPageState extends ConsumerState<DocumentPage> {
  late ListQuery _query = ListQuery(
    path: widget.config.path,
    pageSize: AppConfig.defaultPageSize,
    sortDir: 'desc',
    filters: <String, dynamic>{},
  );
  final TextEditingController _searchController = TextEditingController();
  Timer? _debounce;

  DocumentConfig get config => widget.config;

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

  Future<void> _create() async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => _DocumentFormDialog(config: config),
    );
    if (saved == true && mounted) {
      _reload();
      context.showSuccess('resource.created');
    }
  }

  @override
  Widget build(BuildContext context) {
    final AuthState auth = ref.watch(authProvider);
    final PagedResult<Map<String, dynamic>>? data = ref.watch(listQueryProvider(_query)).valueOrNull;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        PageHeader(
          titleKey: config.nameKey,
          breadcrumbs: config.breadcrumbs,
          actions: <Widget>[
            ...widget.headerActions,
            IconButton(
              tooltip: context.tr('common.refresh'),
              onPressed: _reload,
              icon: const Icon(Icons.refresh),
            ),
            if (config.canCreate && auth.can(config.createPermission))
              FilledButton.icon(
                onPressed: _create,
                icon: const Icon(Icons.add, size: 18),
                label: Text(context.tr('common.new')),
              ),
          ],
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: Wrap(
            spacing: 10,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: <Widget>[
              SizedBox(
                width: 300,
                child: TextField(
                  controller: _searchController,
                  onChanged: _onSearchChanged,
                  decoration: InputDecoration(
                    hintText: context.tr('common.search_hint'),
                    prefixIcon: const Icon(Icons.search, size: 18),
                  ),
                ),
              ),
              SizedBox(
                width: 180,
                child: DropdownButtonFormField<String>(
                  value: _query.filters['status']?.toString(),
                  isExpanded: true,
                  decoration: InputDecoration(labelText: context.tr('common.status')),
                  items: <DropdownMenuItem<String>>[
                    DropdownMenuItem<String>(value: '', child: Text(context.tr('common.all'))),
                    for (final String status in config.statuses)
                      DropdownMenuItem<String>(
                        value: status,
                        child: Text(context.tr(Fmt.statusKey(status))),
                      ),
                  ],
                  onChanged: (String? value) {
                    final Map<String, dynamic> next = Map<String, dynamic>.from(_query.filters);
                    if (value == null || value.isEmpty) {
                      next.remove('status');
                    } else {
                      next['status'] = value;
                    }
                    setState(() => _query = _query.copyWith(page: 1, filters: next));
                  },
                ),
              ),
              _DateFilter(
                labelKey: 'common.from',
                value: _query.filters['date_from']?.toString(),
                onChanged: (String? value) => setState(() {
                  final Map<String, dynamic> next = Map<String, dynamic>.from(_query.filters);
                  if (value == null) {
                    next.remove('date_from');
                  } else {
                    next['date_from'] = value;
                  }
                  _query = _query.copyWith(page: 1, filters: next);
                }),
              ),
              _DateFilter(
                labelKey: 'common.to',
                value: _query.filters['date_to']?.toString(),
                onChanged: (String? value) => setState(() {
                  final Map<String, dynamic> next = Map<String, dynamic>.from(_query.filters);
                  if (value == null) {
                    next.remove('date_to');
                  } else {
                    next['date_to'] = value;
                  }
                  _query = _query.copyWith(page: 1, filters: next);
                }),
              ),
              if (_query.filters.isNotEmpty)
                TextButton.icon(
                  onPressed: () => setState(() => _query = _query.copyWith(page: 1, filters: <String, dynamic>{})),
                  icon: const Icon(Icons.filter_alt_off_outlined, size: 16),
                  label: Text(context.tr('common.reset')),
                ),
              if (data != null)
                Text(
                  '${context.tr('common.total')}: ${data.total}',
                  style: Theme.of(context).textTheme.labelMedium,
                ),
            ],
          ),
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
            child: AsyncView<PagedResult<Map<String, dynamic>>>(
              value: ref.watch(listQueryProvider(_query)),
              onRetry: _reload,
              isEmpty: (PagedResult<Map<String, dynamic>> page) => page.items.isEmpty,
              builder: (PagedResult<Map<String, dynamic>> page) => Column(
                children: <Widget>[
                  Expanded(
                    child: DataTableView(
                      columns: config.columns,
                      rows: page.items,
                      onRowTap: (Map<String, dynamic> row) => _openDetail('${row['id']}'),
                      onSort: (String key, bool ascending) =>
                          setState(() => _query = _query.copyWith(sortBy: key, sortDir: ascending ? 'asc' : 'desc')),
                      sortBy: _query.sortBy,
                      sortDir: _query.sortDir,
                    ),
                  ),
                  PaginationBar(
                    page: page.page,
                    pages: page.pages,
                    total: page.total,
                    pageSize: page.pageSize,
                    onPageChanged: (int pageNumber) => setState(() => _query = _query.copyWith(page: pageNumber)),
                    onPageSizeChanged: (int size) => setState(() => _query = _query.copyWith(page: 1, pageSize: size)),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Future<void> _openDetail(String id) async {
    await showDialog<void>(
      context: context,
      builder: (BuildContext dialogContext) => Dialog(
        insetPadding: const EdgeInsets.all(24),
        child: SizedBox(
          width: 1000,
          height: 700,
          child: _DocumentDetail(config: config, documentId: id, onChanged: _reload),
        ),
      ),
    );
    _reload();
  }
}

class _DateFilter extends StatelessWidget {
  const _DateFilter({required this.labelKey, required this.value, required this.onChanged});

  final String labelKey;
  final String? value;
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 170,
      child: TextField(
        readOnly: true,
        controller: TextEditingController(text: value == null ? '' : Fmt.isoDate(value)),
        decoration: InputDecoration(
          labelText: context.tr(labelKey),
          suffixIcon: IconButton(
            icon: const Icon(Icons.calendar_today, size: 14),
            onPressed: () async {
              final DateTime? picked = await showDatePicker(
                context: context,
                initialDate: Fmt.toDate(value) ?? DateTime.now(),
                firstDate: DateTime(2000),
                lastDate: DateTime(2100),
              );
              if (picked != null) onChanged(Fmt.isoDate(picked));
            },
          ),
        ),
      ),
    );
  }
}

class _DocumentDetail extends ConsumerStatefulWidget {
  const _DocumentDetail({required this.config, required this.documentId, required this.onChanged});

  final DocumentConfig config;
  final String documentId;
  final VoidCallback onChanged;

  @override
  ConsumerState<_DocumentDetail> createState() => _DocumentDetailState();
}

class _DocumentDetailState extends ConsumerState<_DocumentDetail> {
  bool _busy = false;
  List<Map<String, dynamic>> _timeline = <Map<String, dynamic>>[];
  List<Map<String, dynamic>> _attachments = <Map<String, dynamic>>[];

  DocumentConfig get config => widget.config;

  RecordRef get _ref => RecordRef(config.path, widget.documentId);

  void _refresh() {
    ref.invalidate(recordProvider(_ref));
    widget.onChanged();
  }

  Future<void> _run(DocumentActionSpec action) async {
    String? reason;
    if (action.needsReason) {
      reason = await reasonDialog(context, titleKey: action.labelKey);
      if (reason == null) return;
    } else if (action.confirmKey != null) {
      final bool confirmed = await confirmDialog(
        context,
        titleKey: 'common.confirm',
        messageKey: action.confirmKey!,
        confirmKey: 'common.ok',
        destructive: action.destructive,
      );
      if (!confirmed) return;
    }
    setState(() => _busy = true);
    try {
      await ref.read(apiProvider).documentAction(
            config.path,
            widget.documentId,
            action.endpoint,
            body: action.body,
            reason: reason,
          );
      if (mounted) {
        context.showSuccess('common.saved');
        _refresh();
      }
    } catch (error) {
      if (mounted) context.showError(error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _print() async {
    try {
      final DownloadTicket ticket = await ref.read(apiProvider).downloadTicket(
            kind: 'document',
            code: config.permissionPrefix,
            fileFormat: 'print',
            entityId: widget.documentId,
          );
      final Uri? uri = Uri.tryParse(ticket.url);
      if (uri != null) await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (error) {
      if (mounted) context.showError(error);
    }
  }

  Future<void> _loadTimeline() async {
    try {
      final Map<String, dynamic> payload = await ref.read(apiProvider).timeline(config.path, widget.documentId);
      final Object? entries = payload['entries'] ?? payload['items'];
      if (entries is List && mounted) {
        setState(() => _timeline = entries.whereType<Map<String, dynamic>>().toList());
      }
    } catch (_) {
      // The timeline is informational; a failure must not break the document view.
    }
  }

  Future<void> _loadAttachments() async {
    try {
      final PagedResult<Map<String, dynamic>> page = await ref.read(apiProvider).page(
            '/attachments',
            pageSize: 20,
            filters: <String, dynamic>{'entity_type': config.permissionPrefix.split('.').last, 'entity_id': widget.documentId},
          );
      if (mounted) setState(() => _attachments = page.items);
    } catch (_) {
      // Attachments are optional on every document.
    }
  }

  Future<void> _uploadAttachment() async {
    context.showInfo(context.tr('common.upload'));
  }

  @override
  void initState() {
    super.initState();
    _loadTimeline();
    _loadAttachments();
  }

  @override
  Widget build(BuildContext context) {
    final AuthState auth = ref.watch(authProvider);
    final AsyncValue<Map<String, dynamic>> record = ref.watch(recordProvider(_ref));
    final String locale = Localizations.localeOf(context).languageCode;

    return Column(
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 12, 8),
          child: record.maybeWhen(
            data: (Map<String, dynamic> document) => Row(
              children: <Widget>[
                Icon(config.icon ?? Icons.description_outlined, color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        '${document['document_no'] ?? document['code'] ?? widget.documentId}',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      Text(
                        '${Fmt.date(document[config.dateField], locale: locale)} - ${document[config.currencyField] ?? ''}',
                        style: Theme.of(context).textTheme.labelMedium,
                      ),
                    ],
                  ),
                ),
                StatusChip(document['status']),
                const SizedBox(width: 12),
              ],
            ),
            orElse: () => Text(context.tr('common.loading')),
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: AsyncView<Map<String, dynamic>>(
            value: record,
            onRetry: _refresh,
            builder: (Map<String, dynamic> document) => Column(
              children: <Widget>[
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        SectionCard(
                          titleKey: 'common.details',
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: <Widget>[
                              Wrap(
                                children: <Widget>[
                                  for (final FieldSpec field in config.headerFields)
                                    _ReadOnlyValue(field: field, value: document[field.key], locale: locale),
                                ],
                              ),
                              if (config.totals.isNotEmpty) ...<Widget>[
                                const Divider(height: 24),
                                Wrap(
                                  spacing: 24,
                                  runSpacing: 8,
                                  children: <Widget>[
                                    for (final String key in config.totals)
                                      Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: <Widget>[
                                          Text('${context.tr(_labelFor(key))}: ',
                                              style: Theme.of(context).textTheme.labelMedium),
                                          Text(
                                            Fmt.money(
                                              document[key],
                                              locale: locale,
                                              currency: '${document[config.currencyField] ?? ''}',
                                            ),
                                            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                              fontWeight: FontWeight.w600,
                                            ),
                                          ),
                                        ],
                                      ),
                                  ],
                                ),
                              ],
                            ],
                          ),
                        ),
                        const SizedBox(height: 12),
                        SectionCard(
                          titleKey: 'common.lines',
                          child: _lines(document),
                        ),
                        const SizedBox(height: 12),
                        if (_attachments.isNotEmpty)
                          SectionCard(
                            titleKey: 'common.attachments',
                            actions: <Widget>[
                              TextButton.icon(
                                onPressed: _uploadAttachment,
                                icon: const Icon(Icons.upload_file, size: 16),
                                label: Text(context.tr('common.upload')),
                              ),
                            ],
                            child: Column(
                              children: <Widget>[
                                for (final Map<String, dynamic> attachment in _attachments)
                                  ListTile(
                                    dense: true,
                                    leading: const Icon(Icons.attach_file, size: 18),
                                    title: Text('${attachment['file_name'] ?? attachment['title'] ?? ''}'),
                                    subtitle: Text(Fmt.dateTime(attachment['created_at'], locale: locale)),
                                    trailing: IconButton(
                                      icon: const Icon(Icons.download, size: 18),
                                      onPressed: () async {
                                        final Uri? uri = Uri.tryParse(
                                          '${AppConfig.apiBaseUrl}/attachments/${attachment['id']}/download',
                                        );
                                        if (uri != null) await launchUrl(uri, mode: LaunchMode.externalApplication);
                                      },
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        if (_timeline.isNotEmpty) ...<Widget>[
                          const SizedBox(height: 12),
                          SectionCard(
                            titleKey: 'common.timeline',
                            child: Column(
                              children: <Widget>[
                                for (final Map<String, dynamic> entry in _timeline)
                                  ListTile(
                                    dense: true,
                                    leading: const Icon(Icons.history, size: 18),
                                    title: Text('${entry['action'] ?? entry['event'] ?? ''}'),
                                    subtitle: Text(
                                      '${Fmt.dateTime(entry['created_at'], locale: locale)} '
                                      '- ${entry['user_name'] ?? entry['user_email'] ?? ''}',
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                const Divider(height: 1),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: <Widget>[
                      for (final DocumentActionSpec action in <DocumentActionSpec>[
                        ...DocumentConfig.standardActions,
                        ...config.extraActions,
                      ])
                        if (action.isVisibleFor(document['status']?.toString()) &&
                            auth.can(action.permission(config.permissionPrefix)))
                          action.destructive
                              ? OutlinedButton.icon(
                                  onPressed: _busy ? null : () => _run(action),
                                  icon: Icon(action.icon ?? Icons.play_arrow, size: 18, color: Theme.of(context).colorScheme.error),
                                  label: Text(context.tr(action.labelKey)),
                                )
                              : FilledButton.tonalIcon(
                                  onPressed: _busy ? null : () => _run(action),
                                  icon: Icon(action.icon ?? Icons.play_arrow, size: 18),
                                  label: Text(context.tr(action.labelKey)),
                                ),
                      if (auth.can(config.printPermission))
                        OutlinedButton.icon(
                          onPressed: _print,
                          icon: const Icon(Icons.print_outlined, size: 18),
                          label: Text(context.tr('common.print')),
                        ),
                      if (_busy) const Padding(padding: EdgeInsets.all(8), child: CircularProgressIndicator(strokeWidth: 2)),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _lines(Map<String, dynamic> document) {
    final Object? raw = document[config.linesPath];
    final List<Map<String, dynamic>> lines = raw is List
        ? raw.whereType<Map<String, dynamic>>().toList(growable: false)
        : <Map<String, dynamic>>[];
    if (lines.isEmpty) return EmptyState(messageKey: 'common.no_data');
    final List<ColumnSpec> columns = config.lineFields
        .where((FieldSpec field) => field.type != FieldType.hidden)
        .map<ColumnSpec>(
          (FieldSpec field) => ColumnSpec(
            field.key,
            field.labelKey,
            type: field.type,
            align: field.type == FieldType.decimal || field.type == FieldType.integer
                ? MainAxisAlignment.end
                : MainAxisAlignment.start,
          ),
        )
        .toList(growable: false);
    return DataTableView(
      columns: columns,
      rows: lines,
      currencyCode: '${document[config.currencyField] ?? ''}',
    );
  }

  String _labelFor(String key) {
    for (final FieldSpec field in config.headerFields) {
      if (field.key == key) return field.labelKey;
    }
    return switch (key) {
      'subtotal' => 'common.subtotal',
      'discount_amount' => 'common.discount',
      'tax_amount' => 'common.tax',
      'total_amount' => 'common.grand_total',
      'paid_amount' => 'status.paid',
      'balance_amount' => 'common.balance',
      _ => key,
    };
  }
}

class _ReadOnlyValue extends StatelessWidget {
  const _ReadOnlyValue({required this.field, required this.value, required this.locale});

  final FieldSpec field;
  final Object? value;
  final String locale;

  @override
  Widget build(BuildContext context) {
    final String text = switch (field.type) {
      FieldType.decimal => Fmt.money(value, locale: locale),
      FieldType.integer => Fmt.quantity(value, locale: locale),
      FieldType.date => Fmt.date(value, locale: locale),
      FieldType.dateTime => Fmt.dateTime(value, locale: locale),
      FieldType.boolean => Fmt.toBool(value) ? context.tr('common.yes') : context.tr('common.no'),
      _ => value == null || '$value'.isEmpty ? context.tr('common.empty_value') : '$value',
    };
    return SizedBox(
      width: 240,
      child: Padding(
        padding: const EdgeInsets.only(bottom: 10, right: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(context.tr(field.labelKey), style: Theme.of(context).textTheme.labelSmall),
            const SizedBox(height: 2),
            Text(text, style: Theme.of(context).textTheme.bodyMedium),
          ],
        ),
      ),
    );
  }
}

class _DocumentFormDialog extends ConsumerStatefulWidget {
  const _DocumentFormDialog({required this.config});

  final DocumentConfig config;

  @override
  ConsumerState<_DocumentFormDialog> createState() => _DocumentFormDialogState();
}

class _DocumentFormDialogState extends ConsumerState<_DocumentFormDialog> {
  final Map<String, dynamic> _header = <String, dynamic>{};
  final List<Map<String, dynamic>> _lines = <Map<String, dynamic>>[<String, dynamic>{}];
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  bool _saving = false;

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    if (widget.config.lineFields.isNotEmpty && _lines.isEmpty) {
      context.showError(StateError(context.tr('common.lines')));
      return;
    }
    setState(() => _saving = true);
    try {
      final Map<String, dynamic> payload = <String, dynamic>{
        ..._header,
        if (widget.config.lineFields.isNotEmpty)
          'lines': _lines.where((Map<String, dynamic> line) => line.isNotEmpty).toList(),
      };
      await ref.read(apiProvider).create(widget.config.path, payload);
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
    return AlertDialog(
      title: Text('${context.tr('common.new')} - ${context.tr(widget.config.singularKey)}'),
      content: SizedBox(
        width: 900,
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Wrap(
                  children: <Widget>[
                    for (final FieldSpec field in widget.config.headerFields)
                      SpecField(
                        key: ValueKey<String>('header-${field.key}'),
                        spec: field,
                        onChanged: (Object? value) {
                          if (value == null) {
                            _header.remove(field.key);
                          } else {
                            _header[field.key] = value;
                          }
                        },
                      ),
                  ],
                ),
                if (widget.config.lineFields.isNotEmpty) ...<Widget>[
                  const Divider(height: 24),
                  LinesEditor(
                    fields: widget.config.lineFields,
                    lines: _lines,
                    onChanged: (List<Map<String, dynamic>> lines) => setState(() {
                      _lines
                        ..clear()
                        ..addAll(lines);
                    }),
                  ),
                ],
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
