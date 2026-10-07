import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/models/auth_models.dart';
import '../../../core/l10n/app_strings.dart';
import '../../../core/providers.dart';
import '../../../core/utils/formatters.dart';
import '../../../shared/widgets/async_view.dart';
import '../../../shared/widgets/dialogs.dart';
import '../../../shared/widgets/notify.dart';
import '../../../shared/widgets/page_header.dart';
import '../../../shared/widgets/status_chip.dart';

final importEntitiesProvider = FutureProvider.autoDispose<List<Map<String, dynamic>>>(
  (Ref ref) => ref.watch(apiProvider).collection('/data-tools/import/entities'),
);

final exportEntitiesProvider = FutureProvider.autoDispose<List<Map<String, dynamic>>>(
  (Ref ref) => ref.watch(apiProvider).collection('/data-tools/export/entities'),
);

/// Import wizard: choose an entity, paste/upload rows, validate, review the
/// rejected rows (never silently dropped) and commit the valid ones.
class DataImportPage extends ConsumerStatefulWidget {
  const DataImportPage({super.key});

  @override
  ConsumerState<DataImportPage> createState() => _DataImportPageState();
}

class _DataImportPageState extends ConsumerState<DataImportPage> {
  String? _entity;
  final TextEditingController _csv = TextEditingController();
  Map<String, dynamic>? _job;
  bool _busy = false;

  @override
  void dispose() {
    _csv.dispose();
    super.dispose();
  }

  List<Map<String, dynamic>> _rowsFromCsv(String text) {
    final List<String> lines = text
        .split(RegExp(r'\r?\n'))
        .map((String line) => line.trim())
        .where((String line) => line.isNotEmpty)
        .toList();
    if (lines.length < 2) return <Map<String, dynamic>>[];
    final List<String> headers = lines.first.split(',').map((String value) => value.trim()).toList();
    return <Map<String, dynamic>>[
      for (final String line in lines.skip(1))
        <String, dynamic>{
          for (int index = 0; index < headers.length; index++)
            headers[index]: index < line.split(',').length ? line.split(',')[index].trim() : '',
        },
    ];
  }

  Future<void> _createJob() async {
    if (_entity == null) return;
    final List<Map<String, dynamic>> rows = _rowsFromCsv(_csv.text);
    if (rows.isEmpty) {
      context.showError(StateError(context.tr('common.no_data')));
      return;
    }
    setState(() => _busy = true);
    try {
      final Map<String, dynamic> job = await ref.read(apiProvider).create('/data-tools/import/rows', <String, dynamic>{
        'entity_type': _entity,
        'rows': rows,
        'file_name': 'manual-entry.csv',
      });
      final Map<String, dynamic> validated =
          await ref.read(apiProvider).create('/data-tools/import/jobs/${job['id']}/validate', <String, dynamic>{});
      if (mounted) setState(() => _job = <String, dynamic>{...job, ...validated, 'id': job['id']});
    } catch (error) {
      if (mounted) context.showError(error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _commit() async {
    final Map<String, dynamic>? job = _job;
    if (job == null) return;
    setState(() => _busy = true);
    try {
      final Map<String, dynamic> result =
          await ref.read(apiProvider).create('/data-tools/import/jobs/${job['id']}/commit', <String, dynamic>{});
      if (mounted) {
        setState(() => _job = <String, dynamic>{...job, ...result});
        context.showSuccess('common.saved');
      }
    } catch (error) {
      if (mounted) context.showError(error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _uploadFile() async {
    // The API accepts multipart uploads with the same entity metadata.
    setState(() => _busy = true);
    try {
      final List<int> bytes = utf8.encode(_csv.text);
      final FormData form = FormData.fromMap(<String, dynamic>{
        'entity_type': _entity,
        'file': MultipartFile.fromBytes(bytes, filename: 'import.csv'),
      });
      final Map<String, dynamic> job =
          Map<String, dynamic>.from(await ref.read(apiProvider).client.upload('/data-tools/import/upload', form: form) as Map);
      if (mounted) setState(() => _job = job);
    } catch (error) {
      if (mounted) context.showError(error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.only(bottom: 32),
      children: <Widget>[
        PageHeader(
          titleKey: 'data.import',
          breadcrumbs: <String>['nav.data_tools', 'data.import'],
          actions: <Widget>[
            FilledButton.icon(
              onPressed: _busy ? null : _createJob,
              icon: const Icon(Icons.fact_check_outlined, size: 18),
              label: Text(context.tr('data.preview')),
            ),
            const SizedBox(width: 8),
            OutlinedButton.icon(
              onPressed: _busy ? null : _uploadFile,
              icon: const Icon(Icons.upload_file, size: 18),
              label: Text(context.tr('data.upload_file')),
            ),
          ],
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: AsyncView<List<Map<String, dynamic>>>(
            value: ref.watch(importEntitiesProvider),
            onRetry: () => ref.invalidate(importEntitiesProvider),
            isEmpty: (List<Map<String, dynamic>> data) => data.isEmpty,
            builder: (List<Map<String, dynamic>> entities) => Column(
              children: <Widget>[
                Wrap(
                  spacing: 10,
                  runSpacing: 8,
                  children: <Widget>[
                    for (final Map<String, dynamic> entity in entities)
                      ChoiceChip(
                        label: Text('${entity['label'] ?? entity['entity']}'),
                        selected: _entity == '${entity['entity']}',
                        onSelected: (bool selected) => setState(() => _entity = selected ? '${entity['entity']}' : null),
                      ),
                  ],
                ),
                const SizedBox(height: 12),
                SectionCard(
                  titleKey: 'data.upload_file',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        context.tr('common.description'),
                        style: Theme.of(context).textTheme.labelSmall,
                      ),
                      const SizedBox(height: 6),
                      TextField(
                        controller: _csv,
                        maxLines: 8,
                        decoration: const InputDecoration(
                          hintText: 'code,name\nC001,First row\nC002,Second row',
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                if (_job != null) _JobPanel(job: _job!, busy: _busy, onCommit: _commit),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _JobPanel extends StatelessWidget {
  const _JobPanel({required this.job, required this.busy, required this.onCommit});

  final Map<String, dynamic> job;
  final bool busy;
  final VoidCallback onCommit;

  @override
  Widget build(BuildContext context) {
    final Object? errors = job['invalid_rows_data'] ?? job['errors'] ?? job['error_summary'];
    final List<Map<String, dynamic>> errorRows = errors is List ? errors.whereType<Map<String, dynamic>>().toList() : <Map<String, dynamic>>[];
    return SectionCard(
      titleKey: 'data.preview',
      actions: <Widget>[
        FilledButton.icon(
          onPressed: busy ? null : onCommit,
          icon: const Icon(Icons.done_all, size: 18),
          label: Text(context.tr('data.commit')),
        ),
      ],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Wrap(
            spacing: 12,
            runSpacing: 8,
            children: <Widget>[
              CountChip('${context.tr('common.status')}: ${job['status'] ?? ''}'),
              CountChip('${context.tr('common.total')}: ${job['total_rows'] ?? 0}', icon: Icons.list_alt),
              CountChip('${context.tr('data.valid_rows')}: ${job['valid_rows'] ?? 0}', icon: Icons.check_circle_outline),
              CountChip('${context.tr('data.invalid_rows')}: ${job['invalid_rows'] ?? 0}', icon: Icons.error_outline),
              CountChip('${context.tr('common.import')}: ${job['imported_rows'] ?? 0}', icon: Icons.save_outlined),
            ],
          ),
          if (errorRows.isNotEmpty) ...<Widget>[
            const SizedBox(height: 12),
            Text(context.tr('data.errors'), style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 6),
            for (final Map<String, dynamic> row in errorRows.take(50))
              ListTile(
                dense: true,
                leading: const Icon(Icons.error_outline, size: 16),
                title: Text('${context.tr('common.rows')} ${row['row'] ?? row['index'] ?? ''}'),
                subtitle: Text('${row['errors'] ?? row['message'] ?? row['reason'] ?? ''}'),
              ),
          ] else if (job['error_summary'] != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text('${job['error_summary']}'),
            ),
        ],
      ),
    );
  }
}

/// Export every entity as CSV/Excel, and manage backups.
class DataExportPage extends ConsumerWidget {
  const DataExportPage({super.key});

  Future<void> _export(BuildContext context, WidgetRef ref, String entity, String format) async {
    try {
      final DownloadTicket ticket = await ref.read(apiProvider).downloadTicket(kind: 'entity', code: entity, fileFormat: format);
      final Uri? uri = Uri.tryParse(ticket.url);
      if (uri != null) await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (error) {
      if (context.mounted) context.showError(error);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListView(
      padding: const EdgeInsets.only(bottom: 32),
      children: <Widget>[
        PageHeader(titleKey: 'data.export', breadcrumbs: <String>['nav.data_tools', 'data.export']),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: AsyncView<List<Map<String, dynamic>>>(
            value: ref.watch(exportEntitiesProvider),
            onRetry: () => ref.invalidate(exportEntitiesProvider),
            isEmpty: (List<Map<String, dynamic>> data) => data.isEmpty,
            builder: (List<Map<String, dynamic>> entities) => Wrap(
              spacing: 12,
              runSpacing: 12,
              children: <Widget>[
                for (final Map<String, dynamic> entity in entities)
                  SizedBox(
                    width: 320,
                    child: Card(
                      child: ListTile(
                        leading: const Icon(Icons.grid_on_outlined),
                        title: Text('${entity['label'] ?? entity['entity']}'),
                        subtitle: Text('${entity['entity']}'),
                        trailing: PopupMenuButton<String>(
                          onSelected: (String format) => _export(context, ref, '${entity['entity']}', format),
                          itemBuilder: (BuildContext context) => <PopupMenuEntry<String>>[
                            const PopupMenuItem<String>(value: 'csv', child: Text('CSV')),
                            const PopupMenuItem<String>(value: 'xlsx', child: Text('Excel')),
                            PopupMenuItem<String>(value: 'print', child: Text(context.tr('common.print'))),
                          ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// Backup management: create, verify, inspect restore instructions and prune.
class BackupPage extends ConsumerStatefulWidget {
  const BackupPage({super.key});

  @override
  ConsumerState<BackupPage> createState() => _BackupPageState();
}

class _BackupPageState extends ConsumerState<BackupPage> {
  List<Map<String, dynamic>> _backups = <Map<String, dynamic>>[];
  bool _loading = true;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<Map<String, dynamic>> items =
          await ref.read(apiProvider).collection('/data-tools/backup', query: <String, dynamic>{'page_size': 50});
      if (mounted) {
        setState(() {
          _backups = items;
          _loading = false;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _error = error;
          _loading = false;
        });
      }
    }
  }

  Future<void> _create() async {
    try {
      await ref.read(apiProvider).create('/data-tools/backup', <String, dynamic>{'backup_type': 'manual'});
      await _load();
      if (mounted) context.showSuccess('common.saved');
    } catch (error) {
      if (mounted) context.showError(error);
    }
  }

  Future<void> _verify(String id) async {
    try {
      final Map<String, dynamic> result = await ref.read(apiProvider).create(
            '/data-tools/backup/$id/verify',
            <String, dynamic>{},
          );
      if (mounted) {
        await infoDialog(
          context,
          title: context.tr('data.backup_verify'),
          content: Text('${context.tr('common.status')}: ${result['valid'] == true ? context.tr('common.yes') : context.tr('common.no')}\n'
              'checksum: ${result['checksum'] ?? ''}'),
        );
      }
    } catch (error) {
      if (mounted) context.showError(error);
    }
  }

  Future<void> _instructions(String id) async {
    try {
      final Map<String, dynamic> payload = await ref.read(apiProvider).object(
            '/data-tools/backup/$id/restore-instructions',
          );
      final Object? steps = payload['steps'];
      if (mounted) {
        await infoDialog(
          context,
          title: context.tr('data.restore_help'),
          content: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              if (steps is List)
                for (final Object? step in steps) Padding(padding: const EdgeInsets.only(bottom: 6), child: Text('• $step')),
            ],
          ),
        );
      }
    } catch (error) {
      if (mounted) context.showError(error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final String locale = Localizations.localeOf(context).languageCode;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        PageHeader(
          titleKey: 'data.backup',
          breadcrumbs: <String>['nav.data_tools', 'data.backup'],
          actions: <Widget>[
            FilledButton.icon(
              onPressed: _create,
              icon: const Icon(Icons.backup_outlined, size: 18),
              label: Text(context.tr('data.backup_now')),
            ),
            const SizedBox(width: 8),
            IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
          ],
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: _loading
                ? const LoadingState()
                : _error != null
                    ? ErrorState(error: _error!, onRetry: _load)
                    : _backups.isEmpty
                        ? const EmptyState()
                        : ListView.builder(
                            itemCount: _backups.length,
                            itemBuilder: (BuildContext context, int index) {
                              final Map<String, dynamic> backup = _backups[index];
                              return Card(
                                margin: const EdgeInsets.only(bottom: 8),
                                child: ListTile(
                                  leading: const Icon(Icons.archive_outlined),
                                  title: Text('${backup['file_name'] ?? backup['id']}'),
                                  subtitle: Text(
                                    '${backup['backup_type'] ?? ''} · ${Fmt.dateTime(backup['created_at'], locale: locale)} · '
                                    '${backup['size_bytes'] ?? 0} bytes',
                                  ),
                                  trailing: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: <Widget>[
                                      StatusChip(backup['status'] ?? 'completed', compact: true),
                                      IconButton(
                                        tooltip: context.tr('data.backup_verify'),
                                        icon: const Icon(Icons.verified_outlined, size: 18),
                                        onPressed: () => _verify('${backup['id']}'),
                                      ),
                                      IconButton(
                                        tooltip: context.tr('data.restore_help'),
                                        icon: const Icon(Icons.help_outline, size: 18),
                                        onPressed: () => _instructions('${backup['id']}'),
                                      ),
                                    ],
                                  ),
                                ),
                              );
                            },
                          ),
          ),
        ),
      ],
    );
  }
}
