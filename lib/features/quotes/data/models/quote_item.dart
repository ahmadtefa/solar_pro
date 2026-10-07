class QuoteItem {
  final int? id;
  final int quoteId;
  final String description;
  final int quantity;
  final double unitPrice;
  final String unit;
  final String? originCountry;
  final String? warranty;
  final int orderIndex;

  const QuoteItem({
    this.id,
    required this.quoteId,
    required this.description,
    this.quantity = 1,
    this.unitPrice = 0,
    this.unit = 'وحدة',
    this.originCountry,
    this.warranty,
    this.orderIndex = 0,
  });

  factory QuoteItem.create({
    required int quoteId,
    required String description,
    int quantity = 1,
    double unitPrice = 0,
    String unit = 'وحدة',
    String? originCountry,
    String? warranty,
    int orderIndex = 0,
  }) {
    return QuoteItem(
      quoteId: quoteId,
      description: description,
      quantity: quantity,
      unitPrice: unitPrice,
      unit: unit,
      originCountry: originCountry,
      warranty: warranty,
      orderIndex: orderIndex,
    );
  }

  /// Total price of this line (quantity × unit price).
  double get lineTotal => quantity * unitPrice;

  QuoteItem copyWith({
    int? id,
    int? quoteId,
    String? description,
    int? quantity,
    double? unitPrice,
    String? unit,
    String? originCountry,
    String? warranty,
    int? orderIndex,
  }) {
    return QuoteItem(
      id: id ?? this.id,
      quoteId: quoteId ?? this.quoteId,
      description: description ?? this.description,
      quantity: quantity ?? this.quantity,
      unitPrice: unitPrice ?? this.unitPrice,
      unit: unit ?? this.unit,
      originCountry: originCountry ?? this.originCountry,
      warranty: warranty ?? this.warranty,
      orderIndex: orderIndex ?? this.orderIndex,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      if (id != null) 'id': id,
      'quoteId': quoteId,
      'description': description,
      'quantity': quantity,
      'unitPrice': unitPrice,
      'unit': unit,
      'originCountry': originCountry,
      'warranty': warranty,
      'orderIndex': orderIndex,
    };
  }

  factory QuoteItem.fromMap(Map<String, dynamic> map) {
    return QuoteItem(
      id: map['id'] as int?,
      quoteId: map['quoteId'] as int,
      description: map['description'] as String,
      quantity: map['quantity'] as int? ?? 1,
      unitPrice: (map['unitPrice'] as num?)?.toDouble() ?? 0,
      unit: map['unit'] as String? ?? 'وحدة',
      originCountry: map['originCountry'] as String?,
      warranty: map['warranty'] as String?,
      orderIndex: map['orderIndex'] as int? ?? 0,
    );
  }

  Map<String, dynamic> toJson() => toMap();

  factory QuoteItem.fromJson(Map<String, dynamic> json) => QuoteItem.fromMap(json);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is QuoteItem &&
          runtimeType == other.runtimeType &&
          id == other.id &&
          quoteId == other.quoteId &&
          description == other.description &&
          quantity == other.quantity &&
          unitPrice == other.unitPrice &&
          unit == other.unit &&
          originCountry == other.originCountry &&
          warranty == other.warranty &&
          orderIndex == other.orderIndex;

  @override
  int get hashCode {
    return Object.hash(
      id,
      quoteId,
      description,
      quantity,
      unitPrice,
      unit,
      originCountry,
      warranty,
      orderIndex,
    );
  }

  @override
  String toString() {
    return 'QuoteItem(id: $id, quoteId: $quoteId, description: $description, quantity: $quantity, unitPrice: $unitPrice, unit: $unit, originCountry: $originCountry, warranty: $warranty, orderIndex: $orderIndex)';
  }
}
