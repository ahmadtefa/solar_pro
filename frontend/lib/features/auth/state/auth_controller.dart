import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/auth_models.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/providers.dart';
import '../../../core/repository/kayan_api.dart';
import '../../../core/storage/session_store.dart';

/// Owns the signed-in identity: tokens, permissions and company context.
class AuthController extends Notifier<AuthState> {
  @override
  AuthState build() => const AuthState.anonymous();

  KayanApi get _api => ref.read(apiProvider);
  ApiClient get _client => ref.read(apiClientProvider);
  SessionStore get _store => ref.read(sessionStoreProvider);

  bool get isAuthenticated => state.isAuthenticated;

  bool can(String permission) => state.can(permission);

  /// Restore a stored session (called once at start-up).
  Future<void> bootstrap() async {
    final String? refreshToken = _store.refreshToken;
    if (refreshToken == null || refreshToken.isEmpty) {
      state = const AuthState.anonymous();
      return;
    }
    _client.setTokens(
      accessToken: _store.accessToken ?? '',
      refreshToken: refreshToken,
      companyId: _store.companyId,
    );
    // A stale access token is refreshed by the client interceptor.
    await refreshProfile();
  }

  Future<void> login({
    required String email,
    required String password,
    String? companyId,
    String? deviceName,
  }) async {
    final Map<String, dynamic> payload = await _api.create('/auth/login', <String, dynamic>{
      'email': email,
      'password': password,
      if (companyId != null && companyId.isNotEmpty) 'company_id': companyId,
      if (deviceName != null) 'device_name': deviceName,
    });
    final AuthState next = AuthState.fromLogin(payload);
    _client.setTokens(
      accessToken: next.accessToken,
      refreshToken: next.refreshToken,
      companyId: next.companyId,
    );
    await _store.saveSession(
      accessToken: next.accessToken,
      refreshToken: next.refreshToken,
      companyId: next.companyId,
      sessionId: next.sessionId,
    );
    state = next;
    await refreshProfile();
  }

  Future<void> refreshProfile() async {
    if (!state.isAuthenticated && _store.refreshToken == null) {
      state = const AuthState.anonymous();
      return;
    }
    try {
      final Map<String, dynamic> profile = await _api.object('/auth/me');
      state = AuthState.fromProfile(profile, previous: state);
    } on ApiException {
      await _clear();
    }
  }

  Future<void> switchCompany(String companyId) async {
    final Map<String, dynamic> payload = await _api.create('/auth/switch-company', <String, dynamic>{
      'company_id': companyId,
    });
    final AuthState next = AuthState.fromLogin(payload, user: state.user);
    _client.setTokens(accessToken: next.accessToken, refreshToken: next.refreshToken, companyId: next.companyId);
    await _store.saveSession(
      accessToken: next.accessToken,
      refreshToken: next.refreshToken,
      companyId: next.companyId,
      sessionId: next.sessionId,
    );
    state = next;
    await refreshProfile();
  }

  Future<void> changePassword({required String currentPassword, required String newPassword}) async {
    await _api.create('/auth/change-password', <String, dynamic>{
      'current_password': currentPassword,
      'new_password': newPassword,
    });
    state = state.copyWith(mustChangePassword: false);
  }

  Future<void> logout({bool allDevices = false}) async {
    try {
      await _api.create('/auth/logout', <String, dynamic>{'all_devices': allDevices});
    } on ApiException {
      // Signing out must always succeed locally, even with an expired token.
    }
    await _clear();
  }

  /// Called by the HTTP client when the refresh token is refused.
  Future<void> handleExpiredSession() async {
    await _clear();
  }

  Future<void> _clear() async {
    _client.clearTokens();
    await _store.clear();
    state = const AuthState.anonymous();
  }
}
