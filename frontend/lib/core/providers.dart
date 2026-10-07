import 'dart:ui';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/auth/state/auth_controller.dart';
import 'models/auth_models.dart';
import 'network/api_client.dart';
import 'repository/kayan_api.dart';
import 'storage/session_store.dart';

/// Overridden in `main()` once `SharedPreferences` has been opened.
final sessionStoreProvider = Provider<SessionStore>(
  (Ref ref) => throw StateError('sessionStoreProvider must be overridden in main()'),
);

/// The HTTP client, wired so an expired session signs the user out cleanly.
final apiClientProvider = Provider<ApiClient>((Ref ref) {
  final ApiClient client = ApiClient();
  client.onSessionExpired = () async {
    await ref.read(authControllerProvider.notifier).handleExpiredSession();
  };
  return client;
});

final apiProvider = Provider<KayanApi>((Ref ref) => KayanApi(ref.watch(apiClientProvider)));

final authProvider = NotifierProvider<AuthController, AuthState>(AuthController.new);

/// UI preferences: language and theme mode.
class LocaleController extends Notifier<Locale> {
  @override
  Locale build() {
    final String code = ref.watch(sessionStoreProvider).languageCode;
    return Locale(code == 'ar' ? 'ar' : 'en');
  }

  Future<void> toggle() async {
    final Locale next = state.languageCode == 'ar' ? const Locale('en') : const Locale('ar');
    state = next;
    await ref.read(sessionStoreProvider).saveLanguage(next.languageCode);
  }
}

final localeProvider = NotifierProvider<LocaleController, Locale>(LocaleController.new);

class ThemeController extends Notifier<ThemeMode> {
  @override
  ThemeMode build() => ref.watch(sessionStoreProvider).isDarkMode ? ThemeMode.dark : ThemeMode.light;

  Future<void> toggle() async {
    final ThemeMode next = state == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark;
    state = next;
    await ref.read(sessionStoreProvider).saveTheme(next == ThemeMode.dark);
  }
}

final themeModeProvider = NotifierProvider<ThemeController, ThemeMode>(ThemeController.new);
