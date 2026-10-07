import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';

import '../l10n/app_strings.dart';

/// A failure surfaced by the API layer, already translated into something the
/// UI can show: a message key (for localisation) plus the raw server details.
class ApiException implements Exception {
  ApiException({
    required this.message,
    this.statusCode,
    this.code,
    this.details = const <String, dynamic>{},
    this.messageKey,
  });

  final String message;
  final int? statusCode;
  final String? code;
  final Map<String, dynamic> details;

  /// Localisation key used when the UI prefers a translated sentence.
  final String? messageKey;

  bool get isUnauthorised => statusCode == 401;
  bool get isForbidden => statusCode == 403;
  bool get isNotFound => statusCode == 404;
  bool get isValidation => statusCode == 422 || statusCode == 400;
  bool get isConflict => statusCode == 409;
  bool get isNetwork => statusCode == null;

  /// Per-field validation messages returned by the API (`details.fields`).
  Map<String, String> get fieldErrors {
    final Object? fields = details['fields'];
    if (fields is Map) {
      return fields.map<String, String>(
        (Object? key, Object? value) => MapEntry<String, String>('$key', '$value'),
      );
    }
    return const <String, String>{};
  }

  String localized(BuildContext context) {
    if (messageKey != null) {
      return context.tr(messageKey!);
    }
    if (message.isNotEmpty) {
      return message;
    }
    return context.tr('error.unknown');
  }

  factory ApiException.fromDio(DioException error) {
    final Response<dynamic>? response = error.response;
    final Object? data = response?.data;
    String message = error.message ?? '';
    String? code;
    Map<String, dynamic> details = const <String, dynamic>{};
    if (data is Map) {
      message = (data['message'] ?? data['detail'] ?? message).toString();
      code = data['code']?.toString();
      final Object? rawDetails = data['details'];
      if (rawDetails is Map) {
        details = rawDetails.map<String, dynamic>((Object? key, Object? value) => MapEntry<String, String>('$key', value));
      }
    } else if (data is String && data.isNotEmpty) {
      message = data;
    }

    final int? status = response?.statusCode;
    return ApiException(
      message: message.isEmpty ? 'HTTP ${status ?? 'error'}' : message,
      statusCode: status,
      code: code,
      details: details,
      messageKey: _keyForStatus(status),
    );
  }

  static String? _keyForStatus(int? status) {
    switch (status) {
      case 401:
        return 'error.unauthorised';
      case 403:
        return 'error.forbidden';
      case 404:
        return 'error.not_found';
      case 400:
      case 422:
        return 'error.validation';
      case null:
        return 'error.network';
      default:
        return status >= 500 ? 'error.server' : null;
    }
  }

  @override
  String toString() => 'ApiException($statusCode, $code, $message)';
}

/// Thrown when the refresh token is no longer usable: the app must re-authenticate.
class SessionExpiredException extends ApiException {
  SessionExpiredException() : super(message: 'Session expired', statusCode: 401, messageKey: 'error.unauthorised');
}
