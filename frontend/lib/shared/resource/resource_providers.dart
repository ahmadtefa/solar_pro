import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/paged_result.dart';
import '../../core/providers.dart';
import '../../core/repository/kayan_api.dart';
import 'resource_config.dart';

/// Shared data access for the generic resource/document tables.
///
/// Keeping the queries in providers means one lookup table for reference data is
/// fetched once and reused by every dropdown on the screen.
final listQueryProvider = FutureProvider.family<PagedResult<Map<String, dynamic>>, ListQuery>(
  (Ref ref, ListQuery query) {
    return ref.watch(apiProvider).page(
          query.path,
          page: query.page,
          pageSize: query.pageSize,
          q: query.q,
          sortBy: query.sortBy,
          sortDir: query.sortDir,
          filters: query.filters,
        );
  },
);

final recordProvider = FutureProvider.family<Map<String, dynamic>, RecordRef>(
  (Ref ref, RecordRef reference) => ref.watch(apiProvider).object('${reference.path}/${reference.id}'),
);

/// Options for select fields.
///
/// `lookup:<name>` calls `/lookups/<name>`; `list:<path>#<label field>` loads a
/// full list (for example `/customers#name`) so parties can be picked by name.
final optionsProvider = FutureProvider.family<List<LookupOption>, String>((Ref ref, String key) async {
  final KayanApi api = ref.watch(apiProvider);
  if (key.startsWith('lookup:')) {
    return api.lookups(key.substring('lookup:'.length));
  }
  if (key.startsWith('list:')) {
    final String rest = key.substring('list:'.length);
    final int hash = rest.indexOf('#');
    final String path = hash >= 0 ? rest.substring(0, hash) : rest;
    final String labelField = hash >= 0 ? rest.substring(hash + 1) : 'name';
    final List<Map<String, dynamic>> rows = await api.fullList(path, pageSize: 200);
    return rows
        .map<LookupOption>(
          (Map<String, dynamic> row) => LookupOption(
            id: '${row['id']}',
            label: '${row[labelField] ?? row['document_no'] ?? row['full_name'] ?? row['name'] ?? row['code'] ?? row['id']}',
          ),
        )
        .toList(growable: false);
  }
  return const <LookupOption>[];
});
