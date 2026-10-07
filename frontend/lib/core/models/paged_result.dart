/// One page of a paged API collection.
class PagedResult<T> {
  const PagedResult({
    required this.items,
    required this.total,
    required this.page,
    required this.pageSize,
    required this.pages,
  });

  final List<T> items;
  final int total;
  final int page;
  final int pageSize;
  final int pages;

  bool get isEmpty => items.isEmpty;

  bool get hasNext => page < pages;

  static PagedResult<T> fromJson<T>(
    Map<String, dynamic> json,
    T Function(Map<String, dynamic> item) mapper,
  ) {
    final Object? rawItems = json['items'] ?? json['results'] ?? json['rows'];
    final List<T> items = rawItems is List
        ? rawItems.whereType<Map<String, dynamic>>().map<T>(mapper).toList(growable: false)
        : <T>[];
    final int total = _int(json['total']) ?? items.length;
    final int pageSize = _int(json['page_size']) ?? (items.isEmpty ? 25 : items.length);
    return PagedResult<T>(
      items: items,
      total: total,
      page: _int(json['page']) ?? 1,
      pageSize: pageSize,
      pages: _int(json['pages']) ?? (pageSize == 0 ? 1 : ((total + pageSize - 1) ~/ pageSize)),
    );
  }

  static int? _int(Object? value) {
    if (value == null) return null;
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse('$value');
  }

  static const PagedResult<Map<String, dynamic>> empty = PagedResult<Map<String, dynamic>>(
    items: <Map<String, dynamic>>[],
    total: 0,
    page: 1,
    pageSize: 25,
    pages: 1,
  );
}
