class QuoteItem {
  final int? id;
  final int quoteId;
  final String description;
  final int quantity;
  final String? originCountry;
  final String? warranty;
  final int orderIndex;

  const QuoteItem({
    this.id,
    required this.quoteId,
    required this.description,
    this.quantity = 1,
    this.originCountry,
    this.warranty,
    this.orderIndex = 0,
  });

  factory QuoteItem.create({
    required int quoteId,
    required String description,
    int quantity = 1,
    String? originCountry,
    String? warranty,
    int orderIndex = 0,
  }) {
    return QuoteItem(
      quoteId: quoteId,
      description: description,
      quantity: quantity,
      originCountry: originCountry,
      warranty: warranty,
      orderIndex: orderIndex,
    );
  }

  QuoteItem copyWith({
    int? id,
    int? quoteId,
    String? description,
    int? quantity,
    String? originCountry,
    String? warranty,
    int? orderIndex,
  }) {
    return QuoteItem(
      id: id ?? this.id,
      quoteId: quoteId ?? this.quoteId,
      description: description ?? this.description,
      quantity: quantity ?? this.quantity,
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
      originCountry,
      warranty,
      orderIndex,
    );
  }

  @override
  String toString() {
    return 'QuoteItem(id: $id, quoteId: $quoteId, description: $description, quantity: $quantity, originCountry: $originCountry, warranty: $warranty, orderIndex: $orderIndex)';
  }
}
