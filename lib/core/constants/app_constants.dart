class AppConstants {
  AppConstants._();

  // App Information
  static const String appName = 'SolarPro';
  static const String appVersion = '1.0.0';
  static const String appAuthor = 'SolarPro Team';

  // Database
  static const String databaseName = 'solar_pro.db';

  /// Keep in sync with `DatabaseHelper._databaseVersion`.
  static const int databaseVersion = 4;

  // API Configuration (if needed)
  static const String baseUrl = '';
  static const int connectionTimeout = 30000;
  static const int receiveTimeout = 30000;

  // Pagination
  static const int defaultPageSize = 20;

  // Solar Calculations
  static const double solarPanelEfficiency = 0.20; // 20% efficiency
  static const double solarConstant = 1361.0; // W/m²
  static const double averageSunHours = 5.0; // Average peak sun hours

  // Currency
  static const String defaultCurrency = 'SAR';
  static const String currencySymbol = 'ر.س';

  // Default Values
  static const double defaultLatitude = 24.7136; // Riyadh, Saudi Arabia
  static const double defaultLongitude = 46.6753;
  static const double earthRadius = 6371.0; // km

  // Storage Keys
  static const String settingsKey = 'app_settings';
  static const String themeKey = 'theme_mode';
  static const String languageKey = 'app_language';
  static const String tokenKey = 'auth_token';
}
