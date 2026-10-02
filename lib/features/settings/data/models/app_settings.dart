class AppSettings {
  final int? id;
  final String? companyName;
  final String? companyPhone;
  final String? companyLogoPath;
  final double defaultPricePerKw;
  final double defaultPsh;

  const AppSettings({
    this.id,
    this.companyName,
    this.companyPhone,
    this.companyLogoPath,
    this.defaultPricePerKw = 0,
    this.defaultPsh = 5.0,
  });

  factory AppSettings.create({
    String? companyName,
    String? companyPhone,
    String? companyLogoPath,
    double defaultPricePerKw = 0,
    double defaultPsh = 5.0,
  }) {
    return AppSettings(
      companyName: companyName,
      companyPhone: companyPhone,
      companyLogoPath: companyLogoPath,
      defaultPricePerKw: defaultPricePerKw,
      defaultPsh: defaultPsh,
    );
  }

  AppSettings copyWith({
    int? id,
    String? companyName,
    String? companyPhone,
    String? companyLogoPath,
    double? defaultPricePerKw,
    double? defaultPsh,
  }) {
    return AppSettings(
      id: id ?? this.id,
      companyName: companyName ?? this.companyName,
      companyPhone: companyPhone ?? this.companyPhone,
      companyLogoPath: companyLogoPath ?? this.companyLogoPath,
      defaultPricePerKw: defaultPricePerKw ?? this.defaultPricePerKw,
      defaultPsh: defaultPsh ?? this.defaultPsh,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      if (id != null) 'id': id,
      'companyName': companyName,
      'companyPhone': companyPhone,
      'companyLogoPath': companyLogoPath,
      'defaultPricePerKw': defaultPricePerKw,
      'defaultPsh': defaultPsh,
    };
  }

  factory AppSettings.fromMap(Map<String, dynamic> map) {
    return AppSettings(
      id: map['id'] as int?,
      companyName: map['companyName'] as String?,
      companyPhone: map['companyPhone'] as String?,
      companyLogoPath: map['companyLogoPath'] as String?,
      defaultPricePerKw: (map['defaultPricePerKw'] as num?)?.toDouble() ?? 0,
      defaultPsh: (map['defaultPsh'] as num?)?.toDouble() ?? 5.0,
    );
  }

  Map<String, dynamic> toJson() => toMap();

  factory AppSettings.fromJson(Map<String, dynamic> json) => AppSettings.fromMap(json);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is AppSettings &&
          runtimeType == other.runtimeType &&
          id == other.id &&
          companyName == other.companyName &&
          companyPhone == other.companyPhone &&
          companyLogoPath == other.companyLogoPath &&
          defaultPricePerKw == other.defaultPricePerKw &&
          defaultPsh == other.defaultPsh;

  @override
  int get hashCode {
    return Object.hash(
      id,
      companyName,
      companyPhone,
      companyLogoPath,
      defaultPricePerKw,
      defaultPsh,
    );
  }

  @override
  String toString() {
    return 'AppSettings(id: $id, companyName: $companyName, companyPhone: $companyPhone, companyLogoPath: $companyLogoPath, defaultPricePerKw: $defaultPricePerKw, defaultPsh: $defaultPsh)';
  }
}
