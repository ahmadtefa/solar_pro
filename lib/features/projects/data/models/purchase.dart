enum PurchaseType {
  component('component'),
  labor('labor'),
  transport('transport');

  final String value;
  const PurchaseType(this.value);

  static PurchaseType fromString(String value) {
    return PurchaseType.values.firstWhere(
      (e) => e.value == value,
      orElse: () => PurchaseType.component,
    );
  }
}

class Purchase {
  final int? id;
  final int projectId;
  final String itemName;
  final double price;
  final String? supplier;
  final String type;
  final DateTime? purchaseDate;
  final DateTime createdAt;

  const Purchase({
    this.id,
    required this.projectId,
    required this.itemName,
    this.price = 0,
    this.supplier,
    this.type = 'component',
    this.purchaseDate,
    required this.createdAt,
  });

  factory Purchase.create({
    required int projectId,
    required String itemName,
    double price = 0,
    String? supplier,
    String type = 'component',
    DateTime? purchaseDate,
  }) {
    return Purchase(
      projectId: projectId,
      itemName: itemName,
      price: price,
      supplier: supplier,
      type: type,
      purchaseDate: purchaseDate,
      createdAt: DateTime.now(),
    );
  }

  Purchase copyWith({
    int? id,
    int? projectId,
    String? itemName,
    double? price,
    String? supplier,
    String? type,
    DateTime? purchaseDate,
    DateTime? createdAt,
  }) {
    return Purchase(
      id: id ?? this.id,
      projectId: projectId ?? this.projectId,
      itemName: itemName ?? this.itemName,
      price: price ?? this.price,
      supplier: supplier ?? this.supplier,
      type: type ?? this.type,
      purchaseDate: purchaseDate ?? this.purchaseDate,
      createdAt: createdAt ?? this.createdAt,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      if (id != null) 'id': id,
      'projectId': projectId,
      'itemName': itemName,
      'price': price,
      'supplier': supplier,
      'type': type,
      'purchaseDate': purchaseDate?.toIso8601String(),
      'createdAt': createdAt.toIso8601String(),
    };
  }

  factory Purchase.fromMap(Map<String, dynamic> map) {
    return Purchase(
      id: map['id'] as int?,
      projectId: map['projectId'] as int,
      itemName: map['itemName'] as String,
      price: (map['price'] as num?)?.toDouble() ?? 0,
      supplier: map['supplier'] as String?,
      type: map['type'] as String? ?? 'component',
      purchaseDate: map['purchaseDate'] != null ? DateTime.parse(map['purchaseDate'] as String) : null,
      createdAt: DateTime.parse(map['createdAt'] as String),
    );
  }

  Map<String, dynamic> toJson() => toMap();

  factory Purchase.fromJson(Map<String, dynamic> json) => Purchase.fromMap(json);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Purchase &&
          runtimeType == other.runtimeType &&
          id == other.id &&
          projectId == other.projectId &&
          itemName == other.itemName &&
          price == other.price &&
          supplier == other.supplier &&
          type == other.type &&
          purchaseDate == other.purchaseDate &&
          createdAt == other.createdAt;

  @override
  int get hashCode {
    return Object.hash(
      id,
      projectId,
      itemName,
      price,
      supplier,
      type,
      purchaseDate,
      createdAt,
    );
  }

  @override
  String toString() {
    return 'Purchase(id: $id, projectId: $projectId, itemName: $itemName, price: $price, supplier: $supplier, type: $type, purchaseDate: $purchaseDate, createdAt: $createdAt)';
  }
}
