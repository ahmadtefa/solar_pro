import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n/app_strings.dart';
import '../../core/repository/kayan_api.dart';
import '../../core/utils/formatters.dart';
import '../resource/resource_config.dart';
import '../resource/resource_providers.dart';

/// Builds an input widget for a [FieldSpec], wired to the shared option cache.
class SpecField extends ConsumerWidget {
  const SpecField({
    required this.spec,
    this.enabled = true,
    this.onChanged,
    super.key,
  });

  final FieldSpec spec;
  final bool enabled;
  final ValueChanged<Object?>? onChanged;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (spec.type == FieldType.hidden) return const SizedBox.shrink();
    return _SpecFieldBody(spec: spec, enabled: enabled, onChanged: onChanged);
  }
}

class _SpecFieldBody extends ConsumerStatefulWidget {
  const _SpecFieldBody({required this.spec, required this.enabled, this.onChanged});

  final FieldSpec spec;
  final bool enabled;
  final ValueChanged<Object?>? onChanged;

  @override
  ConsumerState<_SpecFieldBody> createState() => _SpecFieldBodyState();
}

class _SpecFieldBodyState extends ConsumerState<_SpecFieldBody> {
  late final TextEditingController _text = TextEditingController(
    text: widget.spec.defaultValue == null ? '' : '${widget.spec.defaultValue}',
  );
  late final TextEditingController _date = TextEditingController(
    text: widget.spec.defaultValue == null ? '' : Fmt.isoDate(widget.spec.defaultValue),
  );
  bool _flag = widget.spec.defaultValue == true;
  String? _selected;

  @override
  void initState() {
    super.initState();
    _text.addListener(_report);
    _date.addListener(_report);
    final Object? initial = widget.spec.defaultValue;
    if (initial != null && initial is String && initial.isNotEmpty) {
      _selected = initial;
    }
  }

  void _report() => setState(() {});

  Object? get value {
    switch (widget.spec.type) {
      case FieldType.boolean:
        return _flag;
      case FieldType.date:
        return _date.text.trim().isEmpty ? null : _date.text.trim();
      case FieldType.integer:
        final String raw = _text.text.trim();
        return raw.isEmpty ? null : int.tryParse(raw);
      case FieldType.decimal:
        final String raw = _text.text.trim();
        return raw.isEmpty ? null : num.tryParse(raw);
      case FieldType.select:
      case FieldType.reference:
        return _selected;
      case FieldType.text:
      case FieldType.multiline:
      case FieldType.dateTime:
      case FieldType.hidden:
        return _text.text.trim().isEmpty ? null : _text.text.trim();
    }
  }

  bool get isValid => !widget.spec.required || _hasValue(value);

  bool _hasValue(Object? candidate) {
    if (candidate == null) return false;
    if (candidate is String) return candidate.isNotEmpty;
    return true;
  }

  @override
  void dispose() {
    _text.dispose();
    _date.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final DateTime now = DateTime.now();
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: Fmt.toDate(_date.text) ?? now,
      firstDate: DateTime(now.year - 10),
      lastDate: DateTime(now.year + 10),
      locale: Localizations.localeOf(context),
    );
    if (picked != null) {
      _date.text = Fmt.isoDate(picked);
      widget.onChanged?.call(_date.text);
    }
  }

  @override
  Widget build(BuildContext context) {
    final String label = context.tr(widget.spec.labelKey);
    final bool enabled = widget.enabled && !widget.spec.readOnly;

    Widget child;
    switch (widget.spec.type) {
      case FieldType.boolean:
        child = Row(
          children: <Widget>[
            Expanded(child: Text(label, style: Theme.of(context).textTheme.bodyMedium)),
            Switch(
              value: _flag,
              onChanged: enabled
                  ? (bool next) {
                      setState(() => _flag = next);
                      widget.onChanged?.call(next);
                    }
                  : null,
            ),
          ],
        );
      case FieldType.date:
        child = TextFormField(
          controller: _date,
          readOnly: true,
          enabled: enabled,
          onTap: enabled ? _pickDate : null,
          decoration: InputDecoration(
            labelText: label,
            suffixIcon: IconButton(icon: const Icon(Icons.calendar_today, size: 16), onPressed: _pickDate),
          ),
          validator: (String? _) => isValid ? null : context.tr('common.required'),
        );
      case FieldType.select:
      case FieldType.reference:
        final List<DropdownOption> staticOptions = widget.spec.options ?? const <DropdownOption>[];
        child = widget.spec.optionsKey == null
            ? _dropdown(context, staticOptions, label, enabled)
            : ref.watch(optionsProvider(widget.spec.optionsKey!)).when(
                  data: (List<LookupOption> options) => _dropdown(
                    context,
                    options.map<DropdownOption>((LookupOption item) => DropdownOption(item.id, item.label)).toList(),
                    label,
                    enabled,
                  ),
                  loading: () => InputDecorator(
                    decoration: InputDecoration(labelText: label),
                    child: const SizedBox(height: 18, child: Center(child: LinearProgressIndicator())),
                  ),
                  error: (Object error, StackTrace stack) => InputDecorator(
                    decoration: InputDecoration(labelText: label, errorText: 'Error'),
                    child: Text('$error', maxLines: 1, overflow: TextOverflow.ellipsis),
                  ),
                );
      case FieldType.multiline:
        child = TextFormField(
          controller: _text,
          enabled: enabled,
          maxLines: widget.spec.maxLines,
          minLines: widget.spec.minLines,
          decoration: InputDecoration(labelText: label, alignLabelWithHint: true),
        );
      default:
        child = TextFormField(
          controller: _text,
          enabled: enabled,
          keyboardType: switch (widget.spec.type) {
            FieldType.integer || FieldType.decimal => const TextInputType.numberWithOptions(decimal: true),
            _ => TextInputType.text,
          },
          inputFormatters: <TextInputFormatter>[
            if (widget.spec.type == FieldType.integer) FilteringTextInputFormatter.digitsOnly,
            if (widget.spec.type == FieldType.decimal)
              FilteringTextInputFormatter.allow(RegExp(r'[0-9.\-]')),
          ],
          decoration: InputDecoration(
            labelText: label,
            helperText: widget.spec.helpKey == null ? null : context.tr(widget.spec.helpKey!),
            prefixIcon: widget.spec.icon == null ? null : Icon(widget.spec.icon, size: 18),
            suffixText: widget.spec.type == FieldType.dateTime ? 'ISO' : null,
          ),
          validator: (String? text) {
            if (!widget.spec.required) return null;
            if (text == null || text.trim().isEmpty) return context.tr('common.required');
            if (widget.spec.type == FieldType.decimal && num.tryParse(text.trim()) == null) {
              return context.tr('error.validation');
            }
            if (widget.spec.type == FieldType.integer && int.tryParse(text.trim()) == null) {
              return context.tr('error.validation');
            }
            return null;
          },
        );
    }

    return SizedBox(
      width: widget.spec.span > 1 ? double.infinity : 320,
      child: Padding(
        padding: const EdgeInsets.only(bottom: 10, right: 8),
        child: child,
      ),
    );
  }

  Widget _dropdown(BuildContext context, List<DropdownOption> options, String label, bool enabled) {
    final bool missing = _selected != null && !options.any((DropdownOption option) => option.value == _selected);
    final List<DropdownMenuItem<String>> items = <DropdownMenuItem<String>>[
      for (final DropdownOption option in options)
        DropdownMenuItem<String>(
          value: option.value,
          child: Text(
            option.label.startsWith('label.') ? context.tr(option.label) : option.label,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      if (missing)
        DropdownMenuItem<String>(value: _selected, child: Text(_selected!, overflow: TextOverflow.ellipsis)),
    ];
    return DropdownButtonFormField<String>(
      value: _selected,
      isExpanded: true,
      decoration: InputDecoration(labelText: label),
      items: items,
      onChanged: enabled
          ? (String? next) {
              setState(() => _selected = next);
              widget.onChanged?.call(next);
            }
          : null,
      validator: (String? _) => isValid ? null : context.tr('common.required'),
    );
  }
}

/// Multi-line editor for document lines inside create/edit forms.
class LinesEditor extends StatefulWidget {
  const LinesEditor({
    required this.fields,
    required this.lines,
    required this.onChanged,
    this.titleKey = 'common.lines',
    super.key,
  });

  final List<FieldSpec> fields;
  final List<Map<String, dynamic>> lines;
  final ValueChanged<List<Map<String, dynamic>>> onChanged;
  final String titleKey;

  @override
  State<LinesEditor> createState() => _LinesEditorState();
}

class _LinesEditorState extends State<LinesEditor> {
  Map<String, dynamic> _blank() => <String, dynamic>{
        for (final FieldSpec field in widget.fields)
          if (field.defaultValue != null) field.key: field.defaultValue,
      };

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(child: Text(context.tr(widget.titleKey), style: theme.textTheme.titleSmall)),
            TextButton.icon(
              onPressed: () => widget.onChanged(<Map<String, dynamic>>[...widget.lines, _blank()]),
              icon: const Icon(Icons.add, size: 16),
              label: Text(context.tr('common.add_line')),
            ),
          ],
        ),
        for (int index = 0; index < widget.lines.length; index++)
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Expanded(
                  child: Wrap(
                    children: <Widget>[
                      for (final FieldSpec field in widget.fields)
                        SpecField(
                          key: ValueKey<String>('line-$index-${field.key}'),
                          spec: FieldSpec(
                            key: field.key,
                            labelKey: field.labelKey,
                            type: field.type,
                            required: field.required,
                            optionsKey: field.optionsKey,
                            options: field.options,
                            defaultValue: widget.lines[index][field.key] ?? field.defaultValue,
                            span: field.span,
                          ),
                          onChanged: (Object? value) {
                            final List<Map<String, dynamic>> next = widget.lines
                                .map<Map<String, dynamic>>((Map<String, dynamic> line) => Map<String, dynamic>.from(line))
                                .toList();
                            if (value == null) {
                              next[index].remove(field.key);
                            } else {
                              next[index][field.key] = value;
                            }
                            widget.onChanged(next);
                          },
                        ),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: context.tr('common.remove_line'),
                  onPressed: widget.lines.length == 1
                      ? null
                      : () {
                          final List<Map<String, dynamic>> next = List<Map<String, dynamic>>.from(widget.lines)..removeAt(index);
                          widget.onChanged(next);
                        },
                  icon: const Icon(Icons.delete_outline, size: 18),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
