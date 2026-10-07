import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/l10n/app_strings.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/providers.dart';
import '../../../core/theme/app_theme.dart';

/// Sign-in screen: bilingual, works on a phone and on a 27" desktop monitor.
class LoginPage extends ConsumerStatefulWidget {
  const LoginPage({super.key});

  @override
  ConsumerState<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends ConsumerState<LoginPage> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _email = TextEditingController();
  final TextEditingController _password = TextEditingController();
  bool _obscure = true;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(authProvider.notifier).login(email: _email.text.trim(), password: _password.text);
    } catch (error) {
      if (mounted) {
        setState(() {
          _busy = false;
          _error = error is ApiException ? error.message : context.tr('login.failed');
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Scaffold(
      body: Row(
        children: <Widget>[
          if (MediaQuery.sizeOf(context).width > 900)
            Expanded(
              child: Container(
                color: AppTheme.seed,
                padding: const EdgeInsets.all(48),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: <Widget>[
                    Text(
                      context.tr('app.name'),
                      style: theme.textTheme.headlineMedium?.copyWith(color: Colors.white, fontWeight: FontWeight.bold),
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          context.tr('app.tagline'),
                          style: theme.textTheme.headlineSmall?.copyWith(color: Colors.white70),
                        ),
                        const SizedBox(height: 16),
                        Text(
                          '${context.tr('nav.sales')} · ${context.tr('nav.inventory')} · '
                          '${context.tr('nav.accounting')} · ${context.tr('nav.hr')}',
                          style: theme.textTheme.bodyLarge?.copyWith(color: Colors.white60),
                        ),
                      ],
                    ),
                    Text(
                      '${context.tr('common.language')} / ${context.tr('common.theme')}',
                      style: theme.textTheme.bodySmall?.copyWith(color: Colors.white38),
                    ),
                  ],
                ),
              ),
            ),
          Expanded(
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(32),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: <Widget>[
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: <Widget>[
                            Expanded(
                              child: Text(context.tr('login.title'), style: theme.textTheme.titleLarge),
                            ),
                            TextButton(
                              onPressed: () => ref.read(localeProvider.notifier).toggle(),
                              child: Text(context.tr('login.language_toggle')),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(
                          context.tr('login.subtitle'),
                          style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                        ),
                        const SizedBox(height: 24),
                        TextFormField(
                          controller: _email,
                          autofillHints: const <String>[AutofillHints.email],
                          keyboardType: TextInputType.emailAddress,
                          decoration: InputDecoration(
                            labelText: context.tr('login.email'),
                            prefixIcon: const Icon(Icons.alternate_email, size: 18),
                          ),
                          validator: (String? value) {
                            if (value == null || value.trim().isEmpty) return context.tr('common.required');
                            if (!value.contains('@')) return context.tr('error.validation');
                            return null;
                          },
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: _password,
                          obscureText: _obscure,
                          autofillHints: const <String>[AutofillHints.password],
                          onFieldSubmitted: (String _) => _submit(),
                          decoration: InputDecoration(
                            labelText: context.tr('login.password'),
                            prefixIcon: const Icon(Icons.lock_outline, size: 18),
                            suffixIcon: IconButton(
                              icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined, size: 18),
                              onPressed: () => setState(() => _obscure = !_obscure),
                            ),
                          ),
                          validator: (String? value) =>
                              (value == null || value.isEmpty) ? context.tr('common.required') : null,
                        ),
                        if (_error != null) ...<Widget>[
                          const SizedBox(height: 12),
                          Container(
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(
                              color: theme.colorScheme.errorContainer,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Row(
                              children: <Widget>[
                                Icon(Icons.error_outline, size: 18, color: theme.colorScheme.onErrorContainer),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    _error!,
                                    style: TextStyle(color: theme.colorScheme.onErrorContainer, fontSize: 12.5),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                        const SizedBox(height: 20),
                        FilledButton.icon(
                          onPressed: _busy ? null : _submit,
                          icon: _busy
                              ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                              : const Icon(Icons.login, size: 18),
                          label: Text(context.tr('login.submit')),
                        ),
                        const SizedBox(height: 14),
                        Text(
                          context.tr('login.demo_hint'),
                          textAlign: TextAlign.center,
                          style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.outline),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
