/// Single Egyptian governorate with Arabic/English names, approximate
/// coordinates, and approximate PSH (Peak Sun Hours per day).
class EgyptGovernorate {
  final int id;
  final String nameAr;
  final String nameEn;
  final double latitude;
  final double longitude;
  final double psh;

  const EgyptGovernorate({
    required this.id,
    required this.nameAr,
    required this.nameEn,
    required this.latitude,
    required this.longitude,
    required this.psh,
  });

  @override
  String toString() => nameAr;
}

/// All 27 Egyptian governorates with realistic approximate PSH values.
const egyptGovernorates = <EgyptGovernorate>[
  EgyptGovernorate(id: 1,  nameAr: 'الإسكندرية',   nameEn: 'Alexandria',   latitude: 31.2,      longitude: 29.9183, psh: 5.2),
  EgyptGovernorate(id: 2,  nameAr: 'البحيرة',       nameEn: 'Dakahlia',      latitude: 30.1167,   longitude: 31.2,    psh: 5.4),
  EgyptGovernorate(id: 3,  nameAr: 'الإسماعيلية',    nameEn: 'Ismailia',      latitude: 30.5833,   longitude: 32.25,   psh: 5.6),
  EgyptGovernorate(id: 4,  nameAr: 'الغربية',       nameEn: 'Al Gharbia',    latitude: 30.85,     longitude: 31.0,    psh: 5.4),
  EgyptGovernorate(id: 5,  nameAr: 'المنوفية',      nameEn: 'Monofiya',      latitude: 30.4833,   longitude: 30.6167, psh: 5.3),
  EgyptGovernorate(id: 6,  nameAr: 'القاهرة',       nameEn: 'Cairo',         latitude: 30.0444,   longitude: 31.2357, psh: 5.8),
  EgyptGovernorate(id: 7,  nameAr: 'الجيزة',        nameEn: 'Giza',          latitude: 29.9333,   longitude: 31.1833, psh: 5.8),
  EgyptGovernorate(id: 8,  nameAr: 'القليوبية',      nameEn: 'Qalyubia',      latitude: 30.1833,   longitude: 31.1667, psh: 5.6),
  EgyptGovernorate(id: 9,  nameAr: 'كفرالشيخ',       nameEn: 'Kafr el-Sheikh',latitude: 31.1333,   longitude: 30.95,   psh: 5.1),
  EgyptGovernorate(id: 10, nameAr: 'مطروح',         nameEn: 'Matruh',        latitude: 31.0,      longitude: 29.3044, psh: 5.0),
  EgyptGovernorate(id: 11, nameAr: 'الوادي الجديد',  nameEn: 'New Valley',    latitude: 25.0,      longitude: 30.0,    psh: 6.3),
  EgyptGovernorate(id: 12, nameAr: 'الفيوم',        nameEn: 'Fayoum',        latitude: 29.0,      longitude: 30.8333, psh: 5.9),
  EgyptGovernorate(id: 13, nameAr: 'بنى سويف',       nameEn: 'Beni Suef',     latitude: 29.0,      longitude: 31.5,    psh: 6.0),
  EgyptGovernorate(id: 14, nameAr: 'البحر الأحمر',   nameEn: 'Red Sea',       latitude: 25.1667,   longitude: 35.0,    psh: 6.6),
  EgyptGovernorate(id: 15, nameAr: 'أسوان',          nameEn: 'Aswan',         latitude: 24.0889,   longitude: 32.8998, psh: 6.5),
  EgyptGovernorate(id: 16, nameAr: 'أسيوط',          nameEn: 'Assiut',        latitude: 27.0,      longitude: 31.1667, psh: 6.4),
  EgyptGovernorate(id: 17, nameAr: 'سوهاج',          nameEn: 'Sohag',         latitude: 26.5558,   longitude: 31.7,    psh: 6.3),
  EgyptGovernorate(id: 18, nameAr: 'المنيا',         nameEn: 'Minya',         latitude: 28.0667,   longitude: 31.2,    psh: 6.0),
  EgyptGovernorate(id: 19, nameAr: 'جنوب سيناء',     nameEn: 'South Sinai',   latitude: 28.5,      longitude: 33.5,    psh: 6.3),
  EgyptGovernorate(id: 20, nameAr: 'الدقهلية',       nameEn: 'Damietta',      latitude: 31.35,     longitude: 31.5,    psh: 5.2),
  EgyptGovernorate(id: 21, nameAr: 'شمال سيناء',     nameEn: 'North Sinai',   latitude: 30.5,      longitude: 33.0,    psh: 6.2),
  EgyptGovernorate(id: 22, nameAr: 'السويس',         nameEn: 'Suez',          latitude: 29.9667,   longitude: 32.5264, psh: 5.7),
  EgyptGovernorate(id: 23, nameAr: 'بورسعيد',        nameEn: 'Port Said',     latitude: 31.2667,   longitude: 32.3,    psh: 5.3),
  EgyptGovernorate(id: 24, nameAr: 'البيهيرة',       nameEn: 'Beheira',       latitude: 30.7833,   longitude: 30.15,   psh: 5.4),
  EgyptGovernorate(id: 25, nameAr: 'الشرقية',        nameEn: 'Sharqia',       latitude: 30.6,      longitude: 31.4,    psh: 5.5),
  EgyptGovernorate(id: 26, nameAr: 'الأقصر',         nameEn: 'Luxor',         latitude: 25.7,      longitude: 32.62,   psh: 6.2),
  EgyptGovernorate(id: 27, nameAr: 'الغردقة',         nameEn: 'Hurghada',      latitude: 27.25,     longitude: 33.8,    psh: 6.1),
];
