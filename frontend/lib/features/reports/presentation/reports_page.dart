import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/l10n/app_strings.dart';
import '../../../core/models/auth_models.dart';
import '../../../core/providers.dart';
import '../../../core/repository/kayan_api.dart';
import '../../../core/utils/formatters.dart';
import '../../../shared/resource/resource_page.dart' show DataTableView;
import '../../../shared/resource/resource_config.dart';
import '../../../shared/widgets/async_view.dart';
import '../../../shared/widgets/dialogs.dart';
import '../../../shared/widgets/notify.dart';
import '../../../shared/widgets/page_header.dart';

/// The report catalogue exposed by the backend report engine.
final reportCatalogueProvider = FutureProvider.autoDispose<List<Map<String, dynamic>>>(
  (Ref ref) => ref.watch(apiProvider).collection('/reports/catalogue'),
);

final savedReportsProvider = FutureProvider.autoDispose<List<Map<String, dynamic>>>(
  (Ref ref) => ref.watch(apiProvider).collection('/reports/saved'),
);

/// Runs any registered report with date/parameter filters and renders the grid
/// the engine returns (columns + rows + totals), with CSV/Excel/PDF/print.
class ReportsPage extends ConsumerStatefulWidget {
  const ReportsPage({this.initialReport, this.savedOnly = false, super.key});

  final String? initialReport;
  final bool savedOnly;

  @override
  ConsumerState<ReportsPage> createState() => _ReportsPageState();
}

class _ReportsPageState extends ConsumerState<ReportsPage> {
  final TextEditingController _dateFrom = TextEditingController(text: DateRange.thisYear().fromIso);
  final TextEditingController _dateTo = TextEditingController(text: DateRange.thisYear().toIso);
  final Map<String, TextEditingController> _parameters = <String, TextEditingController>{};
  String? _selected;
  Map<String, dynamic>? _result;
  bool _running = false;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _selected = widget.initialReport;
  }

  @override
  void dispose() {
    _dateFrom.dispose();
    _dateTo.dispose();
    for (final TextEditingController controller in _parameters.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Map<String, dynamic> _buildParameters(List<Map<String, dynamic>> catalogue) {
    final Map<String, dynamic> parameters = <String, dynamic>{
      'date_from': _dateFrom.text,
      'date_to': _dateTo.text,
    };
    final Map<String, dynamic>? definition = catalogue.firstWhere(
      (Map<String, dynamic> item) => '${item['code']}' == _selected,
      orElse: () => <String, dynamic>{},
    );
    final Object? required = definition['parameters'];
    if (required is List) {
      for (final Object? item in required) {
        final String name = item is Map ? '${item['name'] ?? item['key'] ?? ''}' : '$item';
        if (name.isEmpty) continue;
        final String value = _parameters[name]?.text ?? '';
        if (value.isNotEmpty) parameters[name] = value;
      }
    }
    for (final MapEntry<String, TextEditingController> entry in _parameters.entries) {
      if (entry.value.text.isNotEmpty) parameters[entry.key] = entry.value.text;
    }
    return parameters;
  }

  Future<void> _run(List<Map<String, dynamic>> catalogue) async {
    if (_selected == null) {
      context.showError(StateError(context.tr('reports.catalogue')));
      return;
    }
    setState(() {
      _running = true;
      _error = null;
    });
    try {
      final Map<String, dynamic> result = await ref.read(apiProvider).create(
            '/reports/run/$_selected',
            _buildParameters(catalogue),
          );
      if (mounted) {
        setState(() {
          _result = result;
          _running = false;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _error = error;
          _running = false;
        });
      }
    }
  }

  Future<void> _export(String fileFormat) async {
    if (_selected == null) return;
    try {
      final DownloadTicket ticket = await ref.read(apiProvider).downloadTicket(
            kind: 'report',
            code: _selected!,
            fileFormat: fileFormat,
            parameters: _buildParameters(const <Map<String, dynamic>>[]),
          );
      final Uri? uri = Uri.tryParse(ticket.url);
      if (uri != null) await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (error) {
      if (mounted) context.showError(error);
    }
  }

  Future<void> _saveView() async {
    if (_selected == null) return;
    final String code = 'saved.${DateTime.now().millisecondsSinceEpoch}';
    try {
      await ref.read(apiProvider).create('/reports/saved', <String, dynamic>{
        'code': code,
        'name': _selected,
        'report_type': 'custom',
        'definition': <String, dynamic>{'report_code': _selected, 'parameters': _buildParameters(const <Map<String, dynamic>>[])},
      });
      ref.invalidate(savedReportsProvider);
      if (mounted) context.showSuccess('common.saved');
    } catch (error) {
      if (mounted) context.showError(error);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.savedOnly) return const _SavedReportsPage();
    final AuthState auth = ref.watch(authProvider);
    final String locale = Localizations.localeOf(context).languageCode;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        PageHeader(
          titleKey: 'reports.title',
          breadcrumbs: <String>['nav.reports', 'reports.catalogue'],
          actions: <Widget>[
            if (auth.can('core.report.export')) ...<Widget>[
              OutlinedButton.icon(
                onPressed: () => _export('csv'),
                icon: const Icon(Icons.table_view_outlined, size: 18),
                label: const Text('CSV'),
              ),
              OutlinedButton.icon(
                onPressed: () => _export('xlsx'),
                icon: const Icon(Icons.grid_on_outlined, size: 18),
                label: const Text('Excel'),
              ),
              OutlinedButton.icon(
                onPressed: () => _export('pdf'),
                icon: const Icon(Icons.picture_as_pdf_outlined, size: 18),
                label: const Text('PDF'),
              ),
              OutlinedButton.icon(
                onPressed: () => _export('print'),
                icon: const Icon(Icons.print_outlined, size: 18),
                label: Text(context.tr('common.print')),
              ),
            ],
            if (auth.can('core.saved_report.create'))
              IconButton(
                tooltip: context.tr('reports.save'),
                onPressed: _saveView,
                icon: const Icon(Icons.bookmark_add_outlined),
              ),
          ],
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: AsyncView<List<Map<String, dynamic>>>(
            value: ref.watch(reportCatalogueProvider),
            onRetry: () => ref.invalidate(reportCatalogueProvider),
            isEmpty: (List<Map<String, dynamic>> data) => data.isEmpty,
            builder: (List<Map<String, dynamic>> catalogue) => Wrap(
              spacing: 10,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: <Widget>[
                SizedBox(
                  width: 280,
                  child: DropdownButtonFormField<String>(
                    value: _selected,
                    isExpanded: true,
                    decoration: InputDecoration(labelText: context.tr('reports.catalogue')),
                    items: <DropdownMenuItem<String>>[
                      for (final Map<String, dynamic> report in catalogue)
                        DropdownMenuItem<String>(
                          value: '${report['code']}',
                          child: Text('${report['title'] ?? report['name'] ?? report['code']}'),
                        ),
                    ],
                    onChanged: (String? value) => setState(() => _selected = value),
                  ),
                ),
                _DateField(labelKey: 'common.from', controller: _dateFrom),
                _DateField(labelKey: 'common.to', controller: _dateTo),
                FilledButton.icon(
                  onPressed: _running ? null : () => _run(catalogue),
                  icon: _running
                      ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.play_arrow, size: 18),
                  label: Text(context.tr('reports.run')),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: _error != null
                ? ErrorState(error: _error!, onRetry: () => _run(const <Map<String, dynamic>>[]))
                : _result == null
                    ? const EmptyState(messageKey: 'reports.catalogue', hintKey: 'reports.filters')
                    : _ReportResultView(result: _result!, locale: locale),
          ),
        ),
      ],
    );
  }
}

class _DateField extends StatelessWidget {
  const _DateField({required this.labelKey, required this.controller});

  final String labelKey;
  final TextEditingController controller;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 160,
      child: TextField(
        readOnly: true,
        controller: controller,
        decoration: InputDecoration(
          labelText: context.tr(labelKey),
          suffixIcon: IconButton(
            icon: const Icon(Icons.calendar_today, size: 14),
            onPressed: () async {
              final DateTime? picked = await showDatePicker(
                context: context,
                initialDate: Fmt.toDate(controller.text) ?? DateTime.now(),
                firstDate: DateTime(2000),
                lastDate: DateTime(2100),
              );
              if (picked != null) controller.text = Fmt.isoDate(picked);
            },
          ),
        ),
      ),
    );
  }
}

class _ReportResultView extends StatelessWidget {
  const _ReportResultView({required this.result, required this.locale});

  final Map<String, dynamic> result;
  final String locale;

  @override
  Widget build(BuildContext context) {
    final Object? rawColumns = result['columns'];
    final Object? rawRows = result['rows'];
    final List<Map<String, dynamic>> rows = rawRows is List
        ? rawRows.whereType<Map<String, dynamic>>().toList(growable: false)
        : <Map<String, dynamic>>[];
    final List<ColumnSpec> columns = <ColumnSpec>[
      if (rawColumns is List)
        for (final Object? column in rawColumns)
          if (column is Map<String, dynamic>)
            ColumnSpec(
              '${column['key']}',
              '${column['label'] ?? column['title'] ?? column['key']}',
              type: _typeFor('${column['type'] ?? ''}'),
              align: _typeFor('${column['type'] ?? ''}') == FieldType.decimal
                  ? MainAxisAlignment.end
                  : MainAxisAlignment.start,
            )
          else
            ColumnSpec('$column', '$column'),
    ];
    final Map<String, dynamic> totals = result['totals'] is Map
        ? Map<String, dynamic>.from(result['totals'] as Map<Object?, Object?>)
            .map<String, dynamic>((Object? key, Object? value) => MapEntry<String, dynamic>('$key', value))
        : <String, dynamic>{};

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: Text(
                '${result['title'] ?? result['code'] ?? ''}',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            Text(context.trp('reports.rows', <String, Object>{'count': rows.length})),
          ],
        ),
        const SizedBox(height: 8),
        Expanded(
          child: rows.isEmpty
              ? const EmptyState()
              : DataTableView(
                  columns: columns,
                  rows: rows,
                  onSort: null,
                ),
        ),
        if (totals.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Wrap(
              spacing: 16,
              children: <Widget>[
                for (final MapEntry<String, dynamic> entry in totals.entries)
                  Chip(label: Text('${entry.key}: ${Fmt.money(entry.value, locale: locale)}')),
              ],
            ),
          ),
      ],
    );
  }

  static FieldType _typeFor(String type) {
    switch (type.toLowerCase()) {
      case 'decimal':
      case 'money':
      case 'number':
      case 'numeric':
        return FieldType.decimal;
      case 'int':
      case 'integer':
        return FieldType.integer;
      case 'date':
        return FieldType.date;
      case 'datetime':
        return FieldType.dateTime;
      default:
        return FieldType.text;
    }
  }
}

class _SavedReportsPage extends ConsumerWidget {
  const _SavedReportsPage();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AuthState auth = ref.watch(authProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        PageHeader(
          titleKey: 'reports.saved',
          breadcrumbs: <String>['nav.reports', 'reports.saved'],
          actions: <Widget>[
            IconButton(
              onPressed: () => ref.invalidate(savedReportsProvider),
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: AsyncView<List<Map<String, dynamic>>>(
              value: ref.watch(savedReportsProvider),
              onRetry: () => ref.invalidate(savedReportsProvider),
              isEmpty: (List<Map<String, dynamic>> data) => data.isEmpty,
              builder: (List<Map<String, dynamic>> reports) => ListView.builder(
                itemCount: reports.length,
                itemBuilder: (BuildContext context, int index) {
                  final Map<String, dynamic> report = reports[index];
                  return Card(
                    margin: const EdgeInsets.only(bottom: 8),
                    child: ListTile(
                      leading: const Icon(Icons.insert_chart_outlined),
                      title: Text('${report['name'] ?? report['code']}'),
                      subtitle: Text('${report['report_type'] ?? ''} ${Fmt.dateTime(report['created_at'])}'),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: <Widget>[
                          IconButton(
                            tooltip: context.tr('reports.run'),
                            icon: const Icon(Icons.play_arrow, size: 18),
                            onPressed: () async {
                              try {
                                final Map<String, dynamic> payload =
                                    await ref.read(apiProvider).object('/reports/saved/${report['id']}');
                                final Object? definition = payload['definition'];
                                final String? code = definition is Map ? '${definition['report_code']}' : null;
                                if (code == null || code.isEmpty) return;
                                final Map<String, dynamic> result = await ref.read(apiProvider).create(
                                      '/reports/run/$code',
                                      definition is Map ? Map<String, dynamic>.from(definition['parameters'] ?? <String, dynamic>{}) : <String, dynamic>{},
                                    );
                                if (context.mounted) {
                                  await infoDialog(
                                    context,
                                    title: '${payload['name'] ?? code}',
                                    content: Text('${result['rows'] is List ? (result['rows'] as List).length : 0} rows'),
                                  );
                                }
                              } catch (error) {
                                if (context.mounted) context.showError(error);
                              }
                            },
                          ),
                          if (auth.can('core.saved_report.delete'))
                            IconButton(
                              tooltip: context.tr('common.delete'),
                              icon: const Icon(Icons.delete_outline, size: 18),
                              onPressed: () async {
                                if (!await confirmDialog(context)) return;
                                await ref.read(apiProvider).remove('/reports/saved', '${report['id']}');
                                ref.invalidate(savedReportsProvider);
                              },
                            ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
        ),
      ],
    );
  }
}
