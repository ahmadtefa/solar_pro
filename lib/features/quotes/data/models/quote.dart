enum QuoteStatus {
  draft('draft'),
  sent('sent'),
  accepted('accepted'),
  rejected('rejected'),
  expired('expired');

  final String value;
  const QuoteStatus(this.value);

  static QuoteStatus fromString(String value) {
    return QuoteStatus.values.firstWhere(
      (e) => e.value == value,
      orElse: () => QuoteStatus.draft,
    );
  }
}

class Quote {
  final int? id;
  final int designId;
  final int customerId;
  final double totalPrice;
  final double discount;
  final double tax;
  final String status;
  final DateTime createdAt;

  const Quote({
    this.id,
    required this.designId,
    required this.customerId,
    this.totalPrice = 0,
    this.discount = 0,
    this.tax = 0,
    this.status = 'draft',
    required this.createdAt,
  });

  /// Human friendly reference shown in the UI and on the PDF, e.g. `Q-2026-0007`.
  /// Before the quote is inserted (no id yet) the id part reads `0000`.
  String get displayNumber =>
      'Q-${createdAt.year}-${(id ?? 0).toString().padLeft(4, '0')}';

  factory Quote.create({
    required int designId,
    required int customerId,
    double totalPrice = 0,
    double discount = 0,
    double tax = 0,
    String status = 'draft',
  }) {
    return Quote(
      designId: designId,
      customerId: customerId,
      totalPrice: totalPrice,
      discount: discount,
      tax: tax,
      status: status,
      createdAt: DateTime.now(),
    );
  }

  Quote copyWith({
    int? id,
    int? designId,
    int? customerId,
    double? totalPrice,
    double? discount,
    double? tax,
    String? status,
    DateTime? createdAt,
  }) {
    return Quote(
      id: id ?? this.id,
      designId: designId ?? this.designId,
      customerId: customerId ?? this.customerId,
      totalPrice: totalPrice ?? this.totalPrice,
      discount: discount ?? this.discount,
      tax: tax ?? this.tax,
      status: status ?? this.status,
      createdAt: createdAt ?? this.createdAt,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      if (id != null) 'id': id,
      'designId': designId,
      'customerId': customerId,
      'totalPrice': totalPrice,
      'discount': discount,
      'tax': tax,
      'status': status,
      'createdAt': createdAt.toIso8601String(),
    };
  }

  factory Quote.fromMap(Map<String, dynamic> map) {
    return Quote(
      id: map['id'] as int?,
      designId: map['designId'] as int,
      customerId: map['customerId'] as int,
      totalPrice: (map['totalPrice'] as num?)?.toDouble() ?? 0,
      discount: (map['discount'] as num?)?.toDouble() ?? 0,
      tax: (map['tax'] as num?)?.toDouble() ?? 0,
      status: map['status'] as String? ?? 'draft',
      createdAt: DateTime.parse(map['createdAt'] as String),
    );
  }

  Map<String, dynamic> toJson() => toMap();

  factory Quote.fromJson(Map<String, dynamic> json) => Quote.fromMap(json);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Quote &&
          runtimeType == other.runtimeType &&
          id == other.id &&
          designId == other.designId &&
          customerId == other.customerId &&
          totalPrice == other.totalPrice &&
          discount == other.discount &&
          tax == other.tax &&
          status == other.status &&
          createdAt == other.createdAt;

  @override
  int get hashCode {
    return Object.hash(
      id,
      designId,
      customerId,
      totalPrice,
      discount,
      tax,
      status,
      createdAt,
    );
  }

  @override
  String toString() {
    return 'Quote(id: $id, designId: $designId, customerId: $customerId, totalPrice: $totalPrice, discount: $discount, tax: $tax, status: $status, createdAt: $createdAt)';
  }
}
