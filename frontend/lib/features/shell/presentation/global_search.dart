import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/l10n/app_strings.dart';
import '../../../core/models/auth_models.dart';
import '../../../core/providers.dart';
import '../../../shared/resource/document_config.dart';
import '../../../shared/resource/resource_config.dart';
import '../../modules/module_registry.dart';

/// Command palette: searches every module the user can read and jumps straight
/// to the matching record (the same `/search` engine the rest of the app uses).
Future<void> showGlobalSearch(BuildContext context) {
  return showDialog<void>(
    context: context,
    builder: (BuildContext dialogContext) => const _GlobalSearchDialog(),
  );
}

class _GlobalSearchDialog extends ConsumerStatefulWidget {
  const _GlobalSearchDialog();

  @override
  ConsumerState<_GlobalSearchDialog> createState() => _GlobalSearchDialogState();
}

class _GlobalSearchDialogState extends ConsumerState<_GlobalSearchDialog> {
  final TextEditingController _controller = TextEditingController();
  Timer? _debounce;
  bool _loading = false;
  List<_SearchHit> _hits = <_SearchHit>[];
  String? _error;

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () => _search(value));
  }

  Future<void> _search(String value) async {
    if (value.trim().length < 2) {
      setState(() {
        _hits = <_SearchHit>[];
        _loading = false;
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final Map<String, dynamic> payload = await ref.read(apiProvider).object(
            '/search',
            query: <String, dynamic>{'q': value.trim(), 'limit': 25},
          );
      final List<_SearchHit> hits = <_SearchHit>[];
      final Object? groups = payload['groups'];
      if (groups is Map) {
        groups.forEach((Object? key, Object? value) {
          if (value is List) {
            for (final Object? row in value) {
              if (row is Map<String, dynamic>) {
                hits.add(_SearchHit(group: '$key', data: row));
              }
            }
          }
        });
      }
      final Object? items = payload['items'];
      if (items is List) {
        for (final Object? row in items) {
          if (row is Map<String, dynamic>) hits.add(_SearchHit(group: '${row['entity_type'] ?? 'record'}', data: row));
        }
      }
      if (mounted) {
        setState(() {
          _hits = hits;
          _loading = false;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = context.tr('error.unknown');
        });
      }
    }
  }

  void _open(_SearchHit hit) {
    final String? route = _routeFor(hit);
    Navigator.of(context).pop();
    if (route != null) context.go(route);
  }

  String? _routeFor(_SearchHit hit) {
    final String entity = '${hit.data['entity_type'] ?? hit.data['entity'] ?? hit.group}';
    final String? id = hit.data['id']?.toString();
    for (final MapEntry<String, DocumentConfig> entry in ModuleRegistry.documents.entries) {
      final String prefix = entry.value.permissionPrefix.split('.').last;
      if (entity == prefix || entity == entry.value.permissionPrefix || entity.contains(prefix)) {
        return ModuleRegistry.documentRoute(entry.key);
      }
    }
    for (final MapEntry<String, ResourceConfig> entry in ModuleRegistry.resources.entries) {
      final String prefix = entry.value.permissionPrefix.split('.').last;
      if (entity == prefix || entity == entry.value.permissionPrefix) {
        return ModuleRegistry.resourceRoute(entry.key);
      }
    }
    return id == null ? null : null;
  }

  @override
  Widget build(BuildContext context) {
    final AuthState auth = ref.watch(authProvider);
    return Dialog(
      alignment: Alignment.topCenter,
      insetPadding: const EdgeInsets.only(top: 90, left: 24, right: 24),
      child: SizedBox(
        width: 720,
        height: 520,
        child: Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.all(12),
              child: TextField(
                controller: _controller,
                autofocus: true,
                onChanged: _onChanged,
                decoration: InputDecoration(
                  hintText: context.tr('search.hint'),
                  prefixIcon: const Icon(Icons.search),
                  suffixIcon: _loading
                      ? const Padding(padding: EdgeInsets.all(12), child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)))
                      : null,
                ),
              ),
            ),
            const Divider(height: 1),
            Expanded(
              child: _hits.isEmpty
                  ? _QuickLinks(auth: auth)
                  : ListView.builder(
                      itemCount: _hits.length,
                      itemBuilder: (BuildContext context, int index) {
                        final _SearchHit hit = _hits[index];
                        return ListTile(
                          dense: true,
                          leading: const Icon(Icons.article_outlined, size: 18),
                          title: Text('${hit.data['label'] ?? hit.data['name'] ?? hit.data['document_no'] ?? hit.data['code'] ?? hit.data['id']}'),
                          subtitle: Text('${hit.group} ${hit.data['status'] ?? ''}'),
                          onTap: () => _open(hit),
                        );
                      },
                    ),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.all(8),
                child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
          ],
        ),
      ),
    );
  }
}

class _SearchHit {
  const _SearchHit({required this.group, required this.data});

  final String group;
  final Map<String, dynamic> data;
}

/// When nothing is typed yet the palette offers the modules the user can open.
class _QuickLinks extends ConsumerWidget {
  const _QuickLinks({required this.auth});

  final AuthState auth;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final List<NavItem> items = <NavItem>[
      for (final NavGroup group in ModuleRegistry.navigation())
        for (final NavItem item in group.items)
          if (auth.can(item.permission)) item,
    ];
    return ListView(
      padding: const EdgeInsets.all(8),
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.all(8),
          child: Text(context.tr('search.title'), style: Theme.of(context).textTheme.labelMedium),
        ),
        Wrap(
          children: <Widget>[
            for (final NavItem item in items)
              Padding(
                padding: const EdgeInsets.all(4),
                child: ActionChip(
                  avatar: Icon(item.icon, size: 16),
                  label: Text(context.tr(item.labelKey)),
                  onPressed: () {
                    Navigator.of(context).pop();
                    context.go(item.route);
                  },
                ),
              ),
          ],
        ),
      ],
    );
  }
}
