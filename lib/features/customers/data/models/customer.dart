class Customer {
  final int? id;
  final String name;
  final String? phone;
  final String? address;
  final String locationMethod;
  final int? governorateId;
  final int? cityId;
  final double? latitude;
  final double? longitude;
  final bool pshUsed;
  final DateTime createdAt;

  const Customer({
    this.id,
    required this.name,
    this.phone,
    this.address,
    this.locationMethod = 'manual',
    this.governorateId,
    this.cityId,
    this.latitude,
    this.longitude,
    this.pshUsed = false,
    required this.createdAt,
  });

  factory Customer.create({
    required String name,
    String? phone,
    String? address,
    String locationMethod = 'manual',
    int? governorateId,
    int? cityId,
    double? latitude,
    double? longitude,
    bool pshUsed = false,
  }) {
    return Customer(
      name: name,
      phone: phone,
      address: address,
      locationMethod: locationMethod,
      governorateId: governorateId,
      cityId: cityId,
      latitude: latitude,
      longitude: longitude,
      pshUsed: pshUsed,
      createdAt: DateTime.now(),
    );
  }

  Customer copyWith({
    int? id,
    String? name,
    String? phone,
    String? address,
    String? locationMethod,
    int? governorateId,
    int? cityId,
    double? latitude,
    double? longitude,
    bool? pshUsed,
    DateTime? createdAt,
  }) {
    return Customer(
      id: id ?? this.id,
      name: name ?? this.name,
      phone: phone ?? this.phone,
      address: address ?? this.address,
      locationMethod: locationMethod ?? this.locationMethod,
      governorateId: governorateId ?? this.governorateId,
      cityId: cityId ?? this.cityId,
      latitude: latitude ?? this.latitude,
      longitude: longitude ?? this.longitude,
      pshUsed: pshUsed ?? this.pshUsed,
      createdAt: createdAt ?? this.createdAt,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      if (id != null) 'id': id,
      'name': name,
      'phone': phone,
      'address': address,
      'locationMethod': locationMethod,
      'governorateId': governorateId,
      'cityId': cityId,
      'latitude': latitude,
      'longitude': longitude,
      'pshUsed': pshUsed ? 1 : 0,
      'createdAt': createdAt.toIso8601String(),
    };
  }

  factory Customer.fromMap(Map<String, dynamic> map) {
    return Customer(
      id: map['id'] as int?,
      name: map['name'] as String,
      phone: map['phone'] as String?,
      address: map['address'] as String?,
      locationMethod: map['locationMethod'] as String? ?? 'manual',
      governorateId: map['governorateId'] as int?,
      cityId: map['cityId'] as int?,
      latitude: map['latitude'] as double?,
      longitude: map['longitude'] as double?,
      pshUsed: (map['pshUsed'] as int?) == 1,
      createdAt: DateTime.parse(map['createdAt'] as String),
    );
  }

  Map<String, dynamic> toJson() => toMap();

  factory Customer.fromJson(Map<String, dynamic> json) => Customer.fromMap(json);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Customer &&
          runtimeType == other.runtimeType &&
          id == other.id &&
          name == other.name &&
          phone == other.phone &&
          address == other.address &&
          locationMethod == other.locationMethod &&
          governorateId == other.governorateId &&
          cityId == other.cityId &&
          latitude == other.latitude &&
          longitude == other.longitude &&
          pshUsed == other.pshUsed &&
          createdAt == other.createdAt;

  @override
  int get hashCode {
    return Object.hash(
      id,
      name,
      phone,
      address,
      locationMethod,
      governorateId,
      cityId,
      latitude,
      longitude,
      pshUsed,
      createdAt,
    );
  }

  @override
  String toString() {
    return 'Customer(id: $id, name: $name, phone: $phone, address: $address, locationMethod: $locationMethod, governorateId: $governorateId, cityId: $cityId, latitude: $latitude, longitude: $longitude, pshUsed: $pshUsed, createdAt: $createdAt)';
  }
}
