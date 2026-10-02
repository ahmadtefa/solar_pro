enum ComponentType {
  panel('panel'),
  inverter('inverter');

  final String value;
  const ComponentType(this.value);

  static ComponentType fromString(String value) {
    return ComponentType.values.firstWhere(
      (e) => e.value == value,
      orElse: () => ComponentType.panel,
    );
  }
}

class Component {
  final int? id;
  final String type;
  final String brand;
  final String model;
  final double price;
  final double? pricePerWatt;
  final int? powerW;
  final double? vocV;
  final double? powerKw;
  final double? powerHp;
  final double? maxDcVoltage;
  final DateTime createdAt;

  const Component({
    this.id,
    required this.type,
    required this.brand,
    required this.model,
    this.price = 0,
    this.pricePerWatt,
    this.powerW,
    this.vocV,
    this.powerKw,
    this.powerHp,
    this.maxDcVoltage,
    required this.createdAt,
  });

  factory Component.create({
    required String type,
    required String brand,
    required String model,
    double price = 0,
    double? pricePerWatt,
    int? powerW,
    double? vocV,
    double? powerKw,
    double? powerHp,
    double? maxDcVoltage,
  }) {
    return Component(
      type: type,
      brand: brand,
      model: model,
      price: price,
      pricePerWatt: pricePerWatt,
      powerW: powerW,
      vocV: vocV,
      powerKw: powerKw,
      powerHp: powerHp,
      maxDcVoltage: maxDcVoltage,
      createdAt: DateTime.now(),
    );
  }

  Component copyWith({
    int? id,
    String? type,
    String? brand,
    String? model,
    double? price,
    double? pricePerWatt,
    int? powerW,
    double? vocV,
    double? powerKw,
    double? powerHp,
    double? maxDcVoltage,
    DateTime? createdAt,
  }) {
    return Component(
      id: id ?? this.id,
      type: type ?? this.type,
      brand: brand ?? this.brand,
      model: model ?? this.model,
      price: price ?? this.price,
      pricePerWatt: pricePerWatt ?? this.pricePerWatt,
      powerW: powerW ?? this.powerW,
      vocV: vocV ?? this.vocV,
      powerKw: powerKw ?? this.powerKw,
      powerHp: powerHp ?? this.powerHp,
      maxDcVoltage: maxDcVoltage ?? this.maxDcVoltage,
      createdAt: createdAt ?? this.createdAt,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      if (id != null) 'id': id,
      'type': type,
      'brand': brand,
      'model': model,
      'price': price,
      'pricePerWatt': pricePerWatt,
      'powerW': powerW,
      'vocV': vocV,
      'powerKw': powerKw,
      'powerHp': powerHp,
      'maxDcVoltage': maxDcVoltage,
      'createdAt': createdAt.toIso8601String(),
    };
  }

  factory Component.fromMap(Map<String, dynamic> map) {
    return Component(
      id: map['id'] as int?,
      type: map['type'] as String,
      brand: map['brand'] as String,
      model: map['model'] as String,
      price: (map['price'] as num?)?.toDouble() ?? 0,
      pricePerWatt: (map['pricePerWatt'] as num?)?.toDouble(),
      powerW: map['powerW'] as int?,
      vocV: (map['vocV'] as num?)?.toDouble(),
      powerKw: (map['powerKw'] as num?)?.toDouble(),
      powerHp: (map['powerHp'] as num?)?.toDouble(),
      maxDcVoltage: (map['maxDcVoltage'] as num?)?.toDouble(),
      createdAt: DateTime.parse(map['createdAt'] as String),
    );
  }

  Map<String, dynamic> toJson() => toMap();

  factory Component.fromJson(Map<String, dynamic> json) => Component.fromMap(json);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Component &&
          runtimeType == other.runtimeType &&
          id == other.id &&
          type == other.type &&
          brand == other.brand &&
          model == other.model &&
          price == other.price &&
          pricePerWatt == other.pricePerWatt &&
          powerW == other.powerW &&
          vocV == other.vocV &&
          powerKw == other.powerKw &&
          powerHp == other.powerHp &&
          maxDcVoltage == other.maxDcVoltage &&
          createdAt == other.createdAt;

  @override
  int get hashCode {
    return Object.hash(
      id,
      type,
      brand,
      model,
      price,
      pricePerWatt,
      powerW,
      vocV,
      powerKw,
      powerHp,
      maxDcVoltage,
      createdAt,
    );
  }

  @override
  String toString() {
    return 'Component(id: $id, type: $type, brand: $brand, model: $model, price: $price, pricePerWatt: $pricePerWatt, powerW: $powerW, vocV: $vocV, powerKw: $powerKw, powerHp: $powerHp, maxDcVoltage: $maxDcVoltage, createdAt: $createdAt)';
  }
}
