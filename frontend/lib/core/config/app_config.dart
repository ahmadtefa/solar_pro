/// Compile-time configuration for the Kayan ERP client.
///
/// Values come from `--dart-define` so the same source tree ships to web,
/// desktop and mobile without hardcoding an environment.
class AppConfig {
  const AppConfig._();

  /// Base URL of the versioned API. Defaults to a same-origin relative path so
  /// the web build works behind the Nginx reverse proxy without CORS.
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: '/api/v1',
  );

  static const String appName = 'Kayan ERP';
  static const String appVersion = String.fromEnvironment('APP_VERSION', defaultValue: '1.0.0');

  /// Timeouts (milliseconds) applied by the HTTP client.
  static const int connectTimeout = 20000;
  static const int receiveTimeout = 60000;

  /// Default page size used by every data table.
  static const int defaultPageSize = 25;

  /// Rows offered by the pagination control.
  static const List<int> pageSizes = <int>[10, 25, 50, 100];

  /// Storage keys (namespaced to avoid collisions with other apps on the host).
  static const String tokenKey = 'kayan.access_token';
  static const String refreshTokenKey = 'kayan.refresh_token';
  static const String companyKey = 'kayan.company_id';
  static const String localeKey = 'kayan.locale';
  static const String themeKey = 'kayan.theme_mode';
  static const String sessionKey = 'kayan.session_id';

  /// Locales supported by the client.
  static const List<String> supportedLanguages = <String>['en', 'ar'];
  static const String fallbackLanguage = 'en';
}
