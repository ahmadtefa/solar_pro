import '../models/app_settings.dart';

abstract class SettingsRepository {
  Future<AppSettings?> getSettings();
  Future<int> updateSettings(AppSettings settings);
  Future<void> resetSettings();
}
