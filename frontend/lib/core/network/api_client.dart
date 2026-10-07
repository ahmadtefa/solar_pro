import 'dart:async';

import 'package:dio/dio.dart';

import '../config/app_config.dart';
import 'api_exception.dart';

/// Thin, typed wrapper around Dio.
///
/// Responsibilities kept here (and nowhere else):
///  * the base URL and default headers of every request,
///  * attaching the bearer token,
///  * transparently refreshing an expired access token exactly once per burst
///    of failed requests,
///  * turning every failure into an [ApiException].
class ApiClient {
  ApiClient({Dio? dio}) : _dio = dio ?? Dio() {
    _dio.options = BaseOptions(
      baseUrl: AppConfig.apiBaseUrl,
      connectTimeout: const Duration(milliseconds: AppConfig.connectTimeout),
      receiveTimeout: const Duration(milliseconds: AppConfig.receiveTimeout),
      sendTimeout: const Duration(milliseconds: AppConfig.receiveTimeout),
      responseType: ResponseType.json,
      headers: <String, String>{'Accept': 'application/json'},
      validateStatus: (int? status) => status != null && status < 400,
    );
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (RequestOptions options, RequestInterceptorHandler handler) {
          final String? token = _accessToken;
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: (DioException error, ErrorInterceptorHandler handler) async {
          final bool canRefresh = error.response?.statusCode == 401 &&
              _refreshToken != null &&
              _refreshToken!.isNotEmpty &&
              error.requestOptions.extra['retried'] != true &&
              !error.requestOptions.path.contains('/auth/');
          if (!canRefresh) {
            handler.next(error);
            return;
          }
          final bool refreshed = await refreshTokens();
          if (!refreshed) {
            handler.next(error);
            return;
          }
          try {
            final RequestOptions request = error.requestOptions;
            request.extra['retried'] = true;
            request.headers['Authorization'] = 'Bearer $_accessToken';
            final Response<dynamic> response = await _dio.fetch<dynamic>(request);
            handler.resolve(response);
          } on DioException catch (retryError) {
            handler.next(retryError);
          }
        },
      ),
    );
  }

  final Dio _dio;

  String? _accessToken;
  String? _refreshToken;
  String? _companyId;
  Future<bool>? _refreshing;
  Future<void> Function()? onSessionExpired;

  Dio get raw => _dio;

  void setTokens({required String accessToken, required String refreshToken, String? companyId}) {
    _accessToken = accessToken;
    _refreshToken = refreshToken;
    _companyId = companyId ?? _companyId;
  }

  void updateAccessToken(String accessToken) => _accessToken = accessToken;

  void clearTokens() {
    _accessToken = null;
    _refreshToken = null;
    _companyId = null;
  }

  String? get companyId => _companyId;

  /// Ask the API for a fresh access token. Concurrent callers share one request.
  Future<bool> refreshTokens() {
    final Future<bool>? inFlight = _refreshing;
    if (inFlight != null) return inFlight;
    final Future<bool> attempt = _performRefresh();
    _refreshing = attempt;
    return attempt.whenComplete(() => _refreshing = null);
  }

  Future<bool> _performRefresh() async {
    final String? refreshToken = _refreshToken;
    if (refreshToken == null || refreshToken.isEmpty) return false;
    try {
      final Response<dynamic> response = await Dio(
        BaseOptions(
          baseUrl: AppConfig.apiBaseUrl,
          connectTimeout: const Duration(milliseconds: AppConfig.connectTimeout),
          validateStatus: (int? status) => status != null && status < 400,
        ),
      ).post<dynamic>('/auth/refresh', data: <String, dynamic>{'refresh_token': refreshToken});
      final Map<String, dynamic> body = _asMap(response.data);
      _accessToken = body['access_token']?.toString();
      _refreshToken = body['refresh_token']?.toString() ?? refreshToken;
      _companyId = body['company_id']?.toString() ?? _companyId;
      return _accessToken != null && _accessToken!.isNotEmpty;
    } catch (_) {
      _accessToken = null;
      _refreshToken = null;
      final Future<void> Function()? callback = onSessionExpired;
      if (callback != null) {
        await callback();
      }
      return false;
    }
  }

  // --------------------------------------------------------------- requests
  Future<dynamic> get(String path, {Map<String, dynamic>? query}) => _request(() => _dio.get<dynamic>(path, queryParameters: _clean(query)));

  Future<dynamic> post(String path, {Object? data, Map<String, dynamic>? query}) =>
      _request(() => _dio.post<dynamic>(path, data: data, queryParameters: _clean(query)));

  Future<dynamic> put(String path, {Object? data}) => _request(() => _dio.put<dynamic>(path, data: data));

  Future<dynamic> patch(String path, {Object? data}) => _request(() => _dio.patch<dynamic>(path, data: data));

  Future<dynamic> delete(String path, {Object? data}) => _request(() => _dio.delete<dynamic>(path, data: data));

  Future<dynamic> upload(String path, {required FormData form, Map<String, dynamic>? query}) =>
      _request(() => _dio.post<dynamic>(path, data: form, queryParameters: _clean(query)));

  Future<dynamic> downloadBytes(String path, {Map<String, dynamic>? query}) async {
    try {
      final Response<List<int>> response = await _dio.get<List<int>>(
        path,
        queryParameters: _clean(query),
        options: Options(responseType: ResponseType.bytes),
      );
      return response.data;
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<dynamic> _request(Future<Response<dynamic>> Function() send) async {
    try {
      final Response<dynamic> response = await send();
      return response.data;
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Map<String, dynamic> _clean(Map<String, dynamic>? query) => <String, dynamic>{
        if (query != null)
          for (final MapEntry<String, dynamic> entry in query.entries)
            if (entry.value != null && '${entry.value}' != '') entry.key: entry.value,
      };

  static Map<String, dynamic> _asMap(Object? data) {
    if (data is Map<String, dynamic>) return data;
    if (data is Map) {
      return data.map<String, dynamic>((Object? key, Object? value) => MapEntry<String, dynamic>('$key', value));
    }
    return <String, dynamic>{};
  }
}
