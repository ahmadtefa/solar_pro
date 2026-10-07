import 'dart:typed_data';

import '../config/app_config.dart';
import '../models/auth_models.dart';
import '../models/paged_result.dart';
import '../network/api_client.dart';
import '../network/api_exception.dart';

/// The single place that knows the shape of the Kayan API.
///
/// Widgets never build URLs: they ask for a resource or a document action and
/// receive plain maps/records.
class KayanApi {
  KayanApi(this.client);

  final ApiClient client;

  // ------------------------------------------------------------------ basics
  Future<Map<String, dynamic>> object(String path, {Map<String, dynamic>? query}) async {
    final Object? data = await client.get(path, query: query);
    return _map(data);
  }

  Future<List<Map<String, dynamic>>> collection(String path, {Map<String, dynamic>? query}) async {
    final Object? data = await client.get(path, query: query);
    if (data is List) return _list(data);
    final Map<String, dynamic> body = _map(data);
    final Object? items = body['items'] ?? body['results'] ?? body['rows'];
    return items is List ? _list(items) : <Map<String, dynamic>>[];
  }

  Future<PagedResult<Map<String, dynamic>>> page(
    String path, {
    int page = 1,
    int pageSize = AppConfig.defaultPageSize,
    String? q,
    String? sortBy,
    String? sortDir,
    Map<String, dynamic>? filters,
  }) async {
    final Map<String, dynamic> query = <String, dynamic>{
      'page': page,
      'page_size': pageSize,
      if (q != null && q.isNotEmpty) 'q': q,
      if (sortBy != null && sortBy.isNotEmpty) 'sort_by': sortBy,
      if (sortDir != null && sortDir.isNotEmpty) 'sort_dir': sortDir,
      ...?filters,
    };
    final Object? data = await client.get(path, query: query);
    return PagedResult<Map<String, dynamic>>.fromJson(_map(data), (Map<String, dynamic> item) => item);
  }

  Future<Map<String, dynamic>> create(String path, Map<String, dynamic> body) async =>
      _map(await client.post(path, data: body));

  Future<Map<String, dynamic>> update(String path, String id, Map<String, dynamic> body) async =>
      _map(await client.put('$path/$id', data: body));

  Future<Map<String, dynamic>> patch(String path, String id, Map<String, dynamic> body) async =>
      _map(await client.patch('$path/$id', data: body));

  Future<void> remove(String path, String id) => client.delete('$path/$id');

  // -------------------------------------------------------------- documents
  Future<Map<String, dynamic>> document(String path, String id) async => _map(await client.get('$path/$id'));

  Future<Map<String, dynamic>> documentAction(
    String path,
    String id,
    String action, {
    Map<String, dynamic> body = const <String, dynamic>{},
    String? reason,
  }) async {
    final Map<String, dynamic> payload = <String, dynamic>{
      ...body,
      if (reason != null && reason.isNotEmpty) 'reason': reason,
    };
    if (payload.isEmpty) {
      final Object? data = await client.post('$path/$id/$action');
      return _map(data);
    }
    return _map(await client.post('$path/$id/$action', data: payload));
  }

  Future<void> deleteDocument(String path, String id) => client.delete('$path/$id');

  Future<Map<String, dynamic>> timeline(String path, String id) async => _map(await client.get('$path/$id/timeline'));

  Future<Map<String, dynamic>> printPayload(String path, String id) async =>
      _map(await client.get('$path/$id/print'));

  // ---------------------------------------------------------------- lookups
  Future<List<LookupOption>> lookups(String name, {String? q, int limit = 200}) async {
    final Object? data = await client.get('/lookups/$name', query: <String, dynamic>{'q': q, 'limit': limit});
    final Map<String, dynamic> body = _map(data);
    final Object? items = body['items'];
    if (items is! List) return <LookupOption>[];
    return items.whereType<Map<String, dynamic>>().map<LookupOption>(LookupOption.fromJson).toList(growable: false);
  }

  Future<List<Map<String, dynamic>>> fullList(
    String path, {
    int pageSize = 200,
    Map<String, dynamic>? filters,
    int maxPages = 10,
  }) async {
    final List<Map<String, dynamic>> collected = <Map<String, dynamic>>[];
    for (int page = 1; page <= maxPages; page++) {
      final PagedResult<Map<String, dynamic>> result = await this.page(
        path,
        page: page,
        pageSize: pageSize,
        filters: filters,
      );
      collected.addAll(result.items);
      if (page >= result.pages || result.items.isEmpty) break;
    }
    return collected;
  }

  // ------------------------------------------------------------------ extra
  Future<Map<String, dynamic>> ticket({
    required String kind,
    required String code,
    String fileFormat = 'csv',
    Map<String, dynamic>? parameters,
    String? entityId,
  }) async {
    return _map(
      await client.post(
        '/downloads/tickets',
        data: <String, dynamic>{
          'kind': kind,
          'code': code,
          'file_format': fileFormat,
          if (parameters != null) 'parameters': parameters,
          if (entityId != null) 'entity_id': entityId,
        },
      ),
    );
  }

  Future<DownloadTicket> downloadTicket({
    required String kind,
    required String code,
    String fileFormat = 'csv',
    Map<String, dynamic>? parameters,
    String? entityId,
  }) async {
    return DownloadTicket.fromJson(
      await ticket(
        kind: kind,
        code: code,
        fileFormat: fileFormat,
        parameters: parameters,
        entityId: entityId,
      ),
    );
  }

  Future<Uint8List> attachmentBytes(String path, {Map<String, dynamic>? query}) async {
    final Object? data = await client.downloadBytes(path, query: query);
    if (data is Uint8List) return data;
    if (data is List<int>) return Uint8List.fromList(data);
    throw ApiException(message: 'Unexpected attachment payload');
  }

  static Map<String, dynamic> _map(Object? data) {
    if (data is Map<String, dynamic>) return data;
    if (data is Map) {
      return data.map<String, dynamic>((Object? key, Object? value) => MapEntry<String, dynamic>('$key', value));
    }
    return <String, dynamic>{};
  }

  static List<Map<String, dynamic>> _list(Object raw) => raw
      .whereType<Object>()
      .where((Object? item) => item is Map)
      .map<Map<String, dynamic>>((Object item) => _map(item))
      .toList(growable: false);
}

/// One dropdown entry returned by `/lookups/{name}`.
class LookupOption {
  const LookupOption({required this.id, required this.label});

  final String id;
  final String label;

  factory LookupOption.fromJson(Map<String, dynamic> json) => LookupOption(
        id: '${json['id']}',
        label: '${json['label'] ?? json['name'] ?? json['code'] ?? ''}',
      );

  /// Used by generic filter/field widgets that work with `{id, label}` maps.
  Map<String, String> toMap() => <String, String>{'id': id, 'label': label};
}
