import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/l10n/app_strings.dart';

/// Yes/no confirmation used before destructive actions.
Future<bool> confirmDialog(
  BuildContext context, {
  String titleKey = 'common.confirm',
  String messageKey = 'common.confirm_delete',
  String confirmKey = 'common.delete',
  bool destructive = true,
}) async {
  final bool? answer = await showDialog<bool>(
    context: context,
    builder: (BuildContext dialogContext) => AlertDialog(
      title: Text(dialogContext.tr(titleKey)),
      content: Text(dialogContext.tr(messageKey)),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: Text(dialogContext.tr('common.cancel')),
        ),
        FilledButton(
          style: destructive ? FilledButton.styleFrom(backgroundColor: Theme.of(dialogContext).colorScheme.error) : null,
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: Text(dialogContext.tr(confirmKey)),
        ),
      ],
    ),
  );
  return answer ?? false;
}

/// Collect a mandatory reason (unpost, reject, cancel) with validation.
Future<String?> reasonDialog(
  BuildContext context, {
  required String titleKey,
  String confirmKey = 'common.confirm',
}) async {
  final TextEditingController controller = TextEditingController();
  final GlobalKey<FormState> formKey = GlobalKey<FormState>();
  final String? result = await showDialog<String>(
    context: context,
    builder: (BuildContext dialogContext) => AlertDialog(
      title: Text(dialogContext.tr(titleKey)),
      content: Form(
        key: formKey,
        child: TextFormField(
          controller: controller,
          autofocus: true,
          maxLines: 3,
          decoration: InputDecoration(labelText: dialogContext.tr('common.reason')),
          validator: (String? value) =>
              (value == null || value.trim().isEmpty) ? dialogContext.tr('common.reason_required') : null,
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(),
          child: Text(dialogContext.tr('common.cancel')),
        ),
        FilledButton(
          onPressed: () {
            if (formKey.currentState?.validate() ?? false) {
              Navigator.of(dialogContext).pop(controller.text.trim());
            }
          },
          child: Text(dialogContext.tr(confirmKey)),
        ),
      ],
    ),
  );
  controller.dispose();
  return result;
}

/// Show a plain message inside a dialog (print preview, restore instructions...).
Future<void> infoDialog(BuildContext context, {required String title, required Widget content}) {
  return showDialog<void>(
    context: context,
    builder: (BuildContext dialogContext) => AlertDialog(
      title: Text(title),
      content: SizedBox(width: 720, child: SingleChildScrollView(child: content)),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(),
          child: Text(dialogContext.tr('common.close')),
        ),
      ],
    ),
  );
}
