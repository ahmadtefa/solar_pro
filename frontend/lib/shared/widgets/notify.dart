import 'package:flutter/material.dart';

import '../../core/l10n/app_strings.dart';
import '../../core/network/api_exception.dart';

/// Consistent success/error feedback for every mutation in the app.
extension NotifyContext on BuildContext {
  void showSuccess(String messageKey) {
    ScaffoldMessenger.of(this)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(tr(messageKey)),
          behavior: SnackBarBehavior.floating,
          backgroundColor: Theme.of(this).colorScheme.primary,
        ),
      );
  }

  void showInfo(String message) {
    ScaffoldMessenger.of(this)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message), behavior: SnackBarBehavior.floating));
  }

  void showError(Object error) {
    final String message = error is ApiException ? error.localized(this) : tr('error.unknown');
    ScaffoldMessenger.of(this)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          behavior: SnackBarBehavior.floating,
          backgroundColor: Theme.of(this).colorScheme.error,
        ),
      );
  }
}
