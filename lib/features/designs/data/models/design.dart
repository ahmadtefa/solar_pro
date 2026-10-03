class Design {
  final int? id;
  final int customerId;
  final double capacityKw;
  final String systemType;
  final String customerType;
  final int? inverterId;
  final int? panelId;
  final int panelCount;
  final int stringCount;
  final int panelsPerString;
  final String? notes;
  final DateTime createdAt;

  const Design({
    this.id,
    required this.customerId,
    required this.capacityKw,
    required this.systemType,
    required this.customerType,
    this.inverterId,
    this.panelId,
    this.panelCount = 0,
    this.stringCount = 0,
    this.panelsPerString = 0,
    this.notes,
    required this.createdAt,
  });

  factory Design.create({
    required int customerId,
    required double capacityKw,
    required String systemType,
    required String customerType,
    int? inverterId,
    int? panelId,
    int panelCount = 0,
    int stringCount = 0,
    int panelsPerString = 0,
    String? notes,
  }) {
    return Design(
      customerId: customerId,
      capacityKw: capacityKw,
      systemType: systemType,
      customerType: customerType,
      inverterId: inverterId,
      panelId: panelId,
      panelCount: panelCount,
      stringCount: stringCount,
      panelsPerString: panelsPerString,
      notes: notes,
      createdAt: DateTime.now(),
    );
  }

  Design copyWith({
    int? id,
    int? customerId,
    double? capacityKw,
    String? systemType,
    String? customerType,
    int? inverterId,
    int? panelId,
    int? panelCount,
    int? stringCount,
    int? panelsPerString,
    String? notes,
    DateTime? createdAt,
  }) {
    return Design(
      id: id ?? this.id,
      customerId: customerId ?? this.customerId,
      capacityKw: capacityKw ?? this.capacityKw,
      systemType: systemType ?? this.systemType,
      customerType: customerType ?? this.customerType,
      inverterId: inverterId ?? this.inverterId,
      panelId: panelId ?? this.panelId,
      panelCount: panelCount ?? this.panelCount,
      stringCount: stringCount ?? this.stringCount,
      panelsPerString: panelsPerString ?? this.panelsPerString,
      notes: notes ?? this.notes,
      createdAt: createdAt ?? this.createdAt,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      if (id != null) 'id': id,
      'customerId': customerId,
      'capacityKw': capacityKw,
      'systemType': systemType,
      'customerType': customerType,
      'inverterId': inverterId,
      'panelId': panelId,
      'panelCount': panelCount,
      'stringCount': stringCount,
      'panelsPerString': panelsPerString,
      'notes': notes,
      'createdAt': createdAt.toIso8601String(),
    };
  }

  factory Design.fromMap(Map<String, dynamic> map) {
    return Design(
      id: map['id'] as int?,
      customerId: map['customerId'] as int,
      capacityKw: (map['capacityKw'] as num).toDouble(),
      systemType: map['systemType'] as String,
      customerType: map['customerType'] as String,
      inverterId: map['inverterId'] as int?,
      panelId: map['panelId'] as int?,
      panelCount: map['panelCount'] as int? ?? 0,
      stringCount: map['stringCount'] as int? ?? 0,
      panelsPerString: map['panelsPerString'] as int? ?? 0,
      notes: map['notes'] as String?,
      createdAt: DateTime.parse(map['createdAt'] as String),
    );
  }

  Map<String, dynamic> toJson() => toMap();

  factory Design.fromJson(Map<String, dynamic> json) => Design.fromMap(json);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Design &&
          runtimeType == other.runtimeType &&
          id == other.id &&
          customerId == other.customerId &&
          capacityKw == other.capacityKw &&
          systemType == other.systemType &&
          customerType == other.customerType &&
          inverterId == other.inverterId &&
          panelId == other.panelId &&
          panelCount == other.panelCount &&
          stringCount == other.stringCount &&
          panelsPerString == other.panelsPerString &&
          notes == other.notes &&
          createdAt == other.createdAt;

  @override
  int get hashCode {
    return Object.hash(
      id,
      customerId,
      capacityKw,
      systemType,
      customerType,
      inverterId,
      panelId,
      panelCount,
      stringCount,
      panelsPerString,
      notes,
      createdAt,
    );
  }

  @override
  String toString() {
    return 'Design(id: $id, customerId: $customerId, capacityKw: $capacityKw, systemType: $systemType, customerType: $customerType, inverterId: $inverterId, panelId: $panelId, panelCount: $panelCount, stringCount: $stringCount, panelsPerString: $panelsPerString, notes: $notes, createdAt: $createdAt)';
  }
}
