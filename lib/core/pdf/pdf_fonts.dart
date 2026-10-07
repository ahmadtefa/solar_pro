import 'dart:typed_data';

import 'package:flutter/services.dart' show rootBundle;
import 'package:pdf/widgets.dart' as pw;

/// The pair of fonts a PDF document is built with.
class PdfFonts {
  const PdfFonts({required this.base, required this.bold});

  final pw.Font base;
  final pw.Font bold;
}

/// Loads the fonts bundled with the app.
///
/// Amiri is used because it is the only family we ship with real Arabic glyphs;
/// the fonts that the `pdf` package embeds by default (Helvetica & friends) draw
/// Arabic as empty boxes.
class PdfFontLoader {
  PdfFontLoader._();

  static const String regularAsset = 'assets/fonts/Amiri-Regular.ttf';
  static const String boldAsset = 'assets/fonts/Amiri-Bold.ttf';

  static PdfFonts? _cache;

  /// Loads (and caches) the Arabic fonts used by the PDF generators.
  static Future<PdfFonts> loadArabic() async {
    final cached = _cache;
    if (cached != null) return cached;

    final regular = await rootBundle.load(regularAsset);
    final bold = await rootBundle.load(boldAsset);

    final fonts = PdfFonts(
      base: pw.Font.ttf(regular),
      bold: pw.Font.ttf(bold),
    );
    _cache = fonts;
    return fonts;
  }

  /// Clears the cache - useful in tests.
  static void clearCache() => _cache = null;

  /// Raw font bytes, exposed for tests and for the generator fallback.
  static Future<ByteData> loadRegular() => rootBundle.load(regularAsset);
}
