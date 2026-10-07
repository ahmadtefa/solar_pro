import 'package:shared_preferences/shared_preferences.dart';

import '../config/app_config.dart';

/// Persists tokens and user preferences on the device/browser.
///
/// Only the refresh token and the cosmetic preferences are stored: the access
/// token lives in memory for the duration of the session.
class SessionStore {
  SessionStore(this._preferences);

  final SharedPreferences _preferences;

  static Future<SessionStore> open() async => SessionStore(await SharedPreferences.getInstance());

  String? get accessToken => _preferences.getString(AppConfig.tokenKey);
  String? get refreshToken => _preferences.getString(AppConfig.refreshTokenKey);
  String? get companyId => _preferences.getString(AppConfig.companyKey);
  String? get sessionId => _preferences.getString(AppConfig.sessionKey);

  String get languageCode => _preferences.getString(AppConfig.localeKey) ?? AppConfig.fallbackLanguage;
  bool get isDarkMode => _preferences.getBool(AppConfig.themeKey) ?? false;

  Future<void> saveSession({
    required String accessToken,
    required String refreshToken,
    required String companyId,
    String? sessionId,
  }) async {
    await _preferences.setString(AppConfig.tokenKey, accessToken);
    await _preferences.setString(AppConfig.refreshTokenKey, refreshToken);
    await _preferences.setString(AppConfig.companyKey, companyId);
    if (sessionId != null) {
      await _preferences.setString(AppConfig.sessionKey, sessionId);
    }
  }

  Future<void> saveAccessToken(String accessToken) => _preferences.setString(AppConfig.tokenKey, accessToken);

  Future<void> saveLanguage(String languageCode) => _preferences.setString(AppConfig.localeKey, languageCode);

  Future<void> saveTheme(bool isDark) => _preferences.setBool(AppConfig.themeKey, isDark);

  Future<void> clear() async {
    await _preferences.remove(AppConfig.tokenKey);
    await _preferences.remove(AppConfig.refreshTokenKey);
    await _preferences.remove(AppConfig.sessionKey);
  }
}
