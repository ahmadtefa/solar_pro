/// Minimal, dependency-free support for rendering Arabic text with the `pdf`
/// package.
///
/// The `pdf` package has no contextual analyser: it draws one glyph per code
/// point, so an Arabic word such as "الشمس" is rendered as a row of detached
/// letter forms instead of a connected word. [ArabicText.reshape] converts the
/// logical (input) code points into the Arabic Presentation Forms that a font
/// such as Amiri already contains, which is exactly what the shaping stage of a
/// text engine would do.
///
/// The mapping table below is generated from the Unicode Character Database
/// (decomposition + name of every Arabic presentation form), so it covers the
/// standard Arabic letters plus the extended letters (پ، چ، ژ، گ، ۀ ...).
class ArabicText {
  ArabicText._();

  /// Code point of the Arabic letter LAM (ل), used for the LAM-ALEF ligature.
  static const int _lam = 0x0644;

  /// Presentation forms for every Arabic letter that has contextual variants.
  ///
  /// Offsets: `0` isolated, `1` final, `2` initial, `3` medial.
  /// A `0` entry means "this form does not exist" (which is how the shaping
  /// algorithm knows that e.g. ا or د never connect to the *next* letter).
  static const Map<int, List<int>> _forms = <int, List<int>>{
  0x0621: <int>[0xFE80, 0x0000, 0x0000, 0x0000], // ARABIC LETTER HAMZA
  0x0622: <int>[0xFE81, 0xFE82, 0x0000, 0x0000], // ARABIC LETTER ALEF WITH MADDA ABOVE
  0x0623: <int>[0xFE83, 0xFE84, 0x0000, 0x0000], // ARABIC LETTER ALEF WITH HAMZA ABOVE
  0x0624: <int>[0xFE85, 0xFE86, 0x0000, 0x0000], // ARABIC LETTER WAW WITH HAMZA ABOVE
  0x0625: <int>[0xFE87, 0xFE88, 0x0000, 0x0000], // ARABIC LETTER ALEF WITH HAMZA BELOW
  0x0626: <int>[0xFE89, 0xFE8A, 0xFE8B, 0xFE8C], // ARABIC LETTER YEH WITH HAMZA ABOVE
  0x0627: <int>[0xFE8D, 0xFE8E, 0x0000, 0x0000], // ARABIC LETTER ALEF
  0x0628: <int>[0xFE8F, 0xFE90, 0xFE91, 0xFE92], // ARABIC LETTER BEH
  0x0629: <int>[0xFE93, 0xFE94, 0x0000, 0x0000], // ARABIC LETTER TEH MARBUTA
  0x062A: <int>[0xFE95, 0xFE96, 0xFE97, 0xFE98], // ARABIC LETTER TEH
  0x062B: <int>[0xFE99, 0xFE9A, 0xFE9B, 0xFE9C], // ARABIC LETTER THEH
  0x062C: <int>[0xFE9D, 0xFE9E, 0xFE9F, 0xFEA0], // ARABIC LETTER JEEM
  0x062D: <int>[0xFEA1, 0xFEA2, 0xFEA3, 0xFEA4], // ARABIC LETTER HAH
  0x062E: <int>[0xFEA5, 0xFEA6, 0xFEA7, 0xFEA8], // ARABIC LETTER KHAH
  0x062F: <int>[0xFEA9, 0xFEAA, 0x0000, 0x0000], // ARABIC LETTER DAL
  0x0630: <int>[0xFEAB, 0xFEAC, 0x0000, 0x0000], // ARABIC LETTER THAL
  0x0631: <int>[0xFEAD, 0xFEAE, 0x0000, 0x0000], // ARABIC LETTER REH
  0x0632: <int>[0xFEAF, 0xFEB0, 0x0000, 0x0000], // ARABIC LETTER ZAIN
  0x0633: <int>[0xFEB1, 0xFEB2, 0xFEB3, 0xFEB4], // ARABIC LETTER SEEN
  0x0634: <int>[0xFEB5, 0xFEB6, 0xFEB7, 0xFEB8], // ARABIC LETTER SHEEN
  0x0635: <int>[0xFEB9, 0xFEBA, 0xFEBB, 0xFEBC], // ARABIC LETTER SAD
  0x0636: <int>[0xFEBD, 0xFEBE, 0xFEBF, 0xFEC0], // ARABIC LETTER DAD
  0x0637: <int>[0xFEC1, 0xFEC2, 0xFEC3, 0xFEC4], // ARABIC LETTER TAH
  0x0638: <int>[0xFEC5, 0xFEC6, 0xFEC7, 0xFEC8], // ARABIC LETTER ZAH
  0x0639: <int>[0xFEC9, 0xFECA, 0xFECB, 0xFECC], // ARABIC LETTER AIN
  0x063A: <int>[0xFECD, 0xFECE, 0xFECF, 0xFED0], // ARABIC LETTER GHAIN
  0x0641: <int>[0xFED1, 0xFED2, 0xFED3, 0xFED4], // ARABIC LETTER FEH
  0x0642: <int>[0xFED5, 0xFED6, 0xFED7, 0xFED8], // ARABIC LETTER QAF
  0x0643: <int>[0xFED9, 0xFEDA, 0xFEDB, 0xFEDC], // ARABIC LETTER KAF
  0x0644: <int>[0xFEDD, 0xFEDE, 0xFEDF, 0xFEE0], // ARABIC LETTER LAM
  0x0645: <int>[0xFEE1, 0xFEE2, 0xFEE3, 0xFEE4], // ARABIC LETTER MEEM
  0x0646: <int>[0xFEE5, 0xFEE6, 0xFEE7, 0xFEE8], // ARABIC LETTER NOON
  0x0647: <int>[0xFEE9, 0xFEEA, 0xFEEB, 0xFEEC], // ARABIC LETTER HEH
  0x0648: <int>[0xFEED, 0xFEEE, 0x0000, 0x0000], // ARABIC LETTER WAW
  0x0649: <int>[0xFEEF, 0xFEF0, 0xFBE8, 0xFBE9], // ARABIC LETTER ALEF MAKSURA
  0x064A: <int>[0xFEF1, 0xFEF2, 0xFEF3, 0xFEF4], // ARABIC LETTER YEH
  0x0671: <int>[0xFB50, 0xFB51, 0x0000, 0x0000], // ARABIC LETTER ALEF WASLA
  0x0677: <int>[0xFBDD, 0x0000, 0x0000, 0x0000], // ARABIC LETTER U WITH HAMZA ABOVE
  0x0679: <int>[0xFB66, 0xFB67, 0xFB68, 0xFB69], // ARABIC LETTER TTEH
  0x067A: <int>[0xFB5E, 0xFB5F, 0xFB60, 0xFB61], // ARABIC LETTER TTEHEH
  0x067B: <int>[0xFB52, 0xFB53, 0xFB54, 0xFB55], // ARABIC LETTER BEEH
  0x067E: <int>[0xFB56, 0xFB57, 0xFB58, 0xFB59], // ARABIC LETTER PEH
  0x067F: <int>[0xFB62, 0xFB63, 0xFB64, 0xFB65], // ARABIC LETTER TEHEH
  0x0680: <int>[0xFB5A, 0xFB5B, 0xFB5C, 0xFB5D], // ARABIC LETTER BEHEH
  0x0683: <int>[0xFB76, 0xFB77, 0xFB78, 0xFB79], // ARABIC LETTER NYEH
  0x0684: <int>[0xFB72, 0xFB73, 0xFB74, 0xFB75], // ARABIC LETTER DYEH
  0x0686: <int>[0xFB7A, 0xFB7B, 0xFB7C, 0xFB7D], // ARABIC LETTER TCHEH
  0x0687: <int>[0xFB7E, 0xFB7F, 0xFB80, 0xFB81], // ARABIC LETTER TCHEHEH
  0x0688: <int>[0xFB88, 0xFB89, 0x0000, 0x0000], // ARABIC LETTER DDAL
  0x068C: <int>[0xFB84, 0xFB85, 0x0000, 0x0000], // ARABIC LETTER DAHAL
  0x068D: <int>[0xFB82, 0xFB83, 0x0000, 0x0000], // ARABIC LETTER DDAHAL
  0x068E: <int>[0xFB86, 0xFB87, 0x0000, 0x0000], // ARABIC LETTER DUL
  0x0691: <int>[0xFB8C, 0xFB8D, 0x0000, 0x0000], // ARABIC LETTER RREH
  0x0698: <int>[0xFB8A, 0xFB8B, 0x0000, 0x0000], // ARABIC LETTER JEH
  0x06A4: <int>[0xFB6A, 0xFB6B, 0xFB6C, 0xFB6D], // ARABIC LETTER VEH
  0x06A6: <int>[0xFB6E, 0xFB6F, 0xFB70, 0xFB71], // ARABIC LETTER PEHEH
  0x06A9: <int>[0xFB8E, 0xFB8F, 0xFB90, 0xFB91], // ARABIC LETTER KEHEH
  0x06AD: <int>[0xFBD3, 0xFBD4, 0xFBD5, 0xFBD6], // ARABIC LETTER NG
  0x06AF: <int>[0xFB92, 0xFB93, 0xFB94, 0xFB95], // ARABIC LETTER GAF
  0x06B1: <int>[0xFB9A, 0xFB9B, 0xFB9C, 0xFB9D], // ARABIC LETTER NGOEH
  0x06B3: <int>[0xFB96, 0xFB97, 0xFB98, 0xFB99], // ARABIC LETTER GUEH
  0x06BA: <int>[0xFB9E, 0xFB9F, 0x0000, 0x0000], // ARABIC LETTER NOON GHUNNA
  0x06BB: <int>[0xFBA0, 0xFBA1, 0xFBA2, 0xFBA3], // ARABIC LETTER RNOON
  0x06BE: <int>[0xFBAA, 0xFBAB, 0xFBAC, 0xFBAD], // ARABIC LETTER HEH DOACHASHMEE
  0x06C0: <int>[0xFBA4, 0xFBA5, 0x0000, 0x0000], // ARABIC LETTER HEH WITH YEH ABOVE
  0x06C1: <int>[0xFBA6, 0xFBA7, 0xFBA8, 0xFBA9], // ARABIC LETTER HEH GOAL
  0x06C5: <int>[0xFBE0, 0xFBE1, 0x0000, 0x0000], // ARABIC LETTER KIRGHIZ OE
  0x06C6: <int>[0xFBD9, 0xFBDA, 0x0000, 0x0000], // ARABIC LETTER OE
  0x06C7: <int>[0xFBD7, 0xFBD8, 0x0000, 0x0000], // ARABIC LETTER U
  0x06C8: <int>[0xFBDB, 0xFBDC, 0x0000, 0x0000], // ARABIC LETTER YU
  0x06C9: <int>[0xFBE2, 0xFBE3, 0x0000, 0x0000], // ARABIC LETTER KIRGHIZ YU
  0x06CB: <int>[0xFBDE, 0xFBDF, 0x0000, 0x0000], // ARABIC LETTER VE
  0x06CC: <int>[0xFBFC, 0xFBFD, 0xFBFE, 0xFBFF], // ARABIC LETTER FARSI YEH
  0x06D0: <int>[0xFBE4, 0xFBE5, 0xFBE6, 0xFBE7], // ARABIC LETTER E
  0x06D2: <int>[0xFBAE, 0xFBAF, 0x0000, 0x0000], // ARABIC LETTER YEH BARREE
  0x06D3: <int>[0xFBB0, 0xFBB1, 0x0000, 0x0000], // ARABIC LETTER YEH BARREE WITH HAMZA ABOVE
  };

  /// LAM-ALEF ligatures: `[isolated, final]` for each ALEF-like letter.
  static const Map<int, List<int>> _lamAlef = <int, List<int>>{
    0x0627: <int>[0xFEFB, 0xFEFC], // ا ALEF
    0x0622: <int>[0xFEF5, 0xFEF6], // آ ALEF WITH MADDA ABOVE
    0x0623: <int>[0xFEF7, 0xFEF8], // أ ALEF WITH HAMZA ABOVE
    0x0625: <int>[0xFEF9, 0xFEFA], // إ ALEF WITH HAMZA BELOW
  };

  /// True when [codeUnit] can be joined to the letter that follows it.
  static bool joinsWithNext(int codeUnit) {
    final forms = _forms[codeUnit];
    if (forms == null) return false;
    return forms[2] != 0 || forms[3] != 0;
  }

  /// True when [codeUnit] can be joined to the letter that precedes it.
  static bool joinsWithPrevious(int codeUnit) {
    final forms = _forms[codeUnit];
    if (forms == null) return false;
    return forms[1] != 0 || forms[3] != 0;
  }

  /// True when [codeUnit] is an Arabic letter that needs contextual shaping.
  static bool isShapedLetter(int codeUnit) => _forms.containsKey(codeUnit);

  /// Returns [text] with every Arabic letter replaced by the presentation form
  /// matching its position in the word.
  ///
  /// Non Arabic characters (digits, Latin text, punctuation, spaces) are left
  /// untouched and - just like in real Arabic typography - they break the
  /// connection between the letters around them.
  ///
  /// ```dart
  /// ArabicText.reshape('الشمس'); // connected word, ready for the pdf package
  /// ```
  static String reshape(String text) {
    final units = text.codeUnits;
    final out = <int>[];

    for (var i = 0; i < units.length; i++) {
      final unit = units[i];
      final forms = _forms[unit];
      if (forms == null) {
        out.add(unit); // not an Arabic letter: pass through unchanged
        continue;
      }

      // Connection with the previous letter.
      final previous = i > 0 ? units[i - 1] : 0;
      final linkedToPrevious =
          previous != 0 && joinsWithNext(previous) && joinsWithPrevious(unit);

      // LAM + ALEF is drawn as one glyph in Arabic typography.
      if (unit == _lam && i + 1 < units.length) {
        final ligature = _lamAlef[units[i + 1]];
        if (ligature != null) {
          out.add(linkedToPrevious ? ligature[1] : ligature[0]);
          i++; // the ALEF is consumed by the ligature
          continue;
        }
      }

      // Connection with the next letter.
      final next = i + 1 < units.length ? units[i + 1] : 0;
      final linkedToNext =
          next != 0 && joinsWithNext(unit) && joinsWithPrevious(next);

      final int glyph;
      if (linkedToPrevious && linkedToNext && forms[3] != 0) {
        glyph = forms[3]; // medial
      } else if (linkedToPrevious && forms[1] != 0) {
        glyph = forms[1]; // final
      } else if (linkedToNext && forms[2] != 0) {
        glyph = forms[2]; // initial
      } else {
        glyph = forms[0]; // isolated
      }
      out.add(glyph);
    }

    return String.fromCharCodes(out);
  }

  /// Number of distinct letters covered by the table (useful in tests/docs).
  static int get coveredLetters => _forms.length;

}
