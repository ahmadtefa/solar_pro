import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppTheme {
  AppTheme._();

  // Colors
  static const primaryColor = Color(0xFF2E7D32); // Green
  static const primaryDarkColor = Color(0xFF1B5E20); // Dark Green
  static const secondaryColor = Color(0xFFF57C00); // Orange
  static const accentColor = Color(0xFF0288D1); // Blue

  // Light Theme
  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: ColorScheme.light(
        primary: primaryColor,
        primaryContainer: primaryColor.withValues(alpha: 0.12),
        secondary: secondaryColor,
        secondaryContainer: secondaryColor.withValues(alpha: 0.12),
        tertiary: accentColor,
        tertiaryContainer: accentColor.withValues(alpha: 0.12),
        surface: Colors.white,
        onPrimary: Colors.white,
        onSecondary: Colors.white,
        onSurface: Colors.black87,
        surfaceContainerHighest: const Color(0xFFF5F5F5),
      ),
      scaffoldBackgroundColor: const Color(0xFFFAFAFA),
      appBarTheme: AppBarTheme(
        backgroundColor: primaryColor,
        foregroundColor: Colors.white,
        elevation: 0,
        centerTitle: true,
        titleTextStyle: GoogleFonts.amiri(
          fontSize: 20,
          fontWeight: FontWeight.bold,
          color: Colors.white,
        ),
      ),
      cardTheme: CardThemeData(
        elevation: 2,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primaryColor,
          foregroundColor: Colors.white,
          elevation: 2,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
          textStyle: GoogleFonts.amiri(
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: primaryColor,
          side: const BorderSide(color: primaryColor, width: 2),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
          textStyle: GoogleFonts.amiri(
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: primaryColor,
          textStyle: GoogleFonts.amiri(
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Colors.grey),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Color(0xFFBDBDBD)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: primaryColor, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Colors.red, width: 1),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Colors.red, width: 2),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        labelStyle: GoogleFonts.amiri(
          fontSize: 14,
          color: const Color(0xFF757575),
        ),
        hintStyle: GoogleFonts.amiri(
          fontSize: 14,
          color: const Color(0xFFBDBDBD),
        ),
      ),
      floatingActionButtonTheme: FloatingActionButtonThemeData(
        backgroundColor: primaryColor,
        foregroundColor: Colors.white,
        elevation: 4,
      ),
      dividerTheme: DividerThemeData(
        color: const Color(0xFFE0E0E0),
        thickness: 1,
      ),
      textTheme: TextTheme(
        displayLarge: GoogleFonts.amiri(fontSize: 32, fontWeight: FontWeight.bold, color: const Color(0xFF212121)),
        displayMedium: GoogleFonts.amiri(fontSize: 28, fontWeight: FontWeight.bold, color: const Color(0xFF212121)),
        displaySmall: GoogleFonts.amiri(fontSize: 24, fontWeight: FontWeight.bold, color: const Color(0xFF212121)),
        headlineLarge: GoogleFonts.amiri(fontSize: 22, fontWeight: FontWeight.w600, color: const Color(0xFF212121)),
        headlineMedium: GoogleFonts.amiri(fontSize: 20, fontWeight: FontWeight.w600, color: const Color(0xFF212121)),
        headlineSmall: GoogleFonts.amiri(fontSize: 18, fontWeight: FontWeight.w600, color: const Color(0xFF212121)),
        titleLarge: GoogleFonts.amiri(fontSize: 16, fontWeight: FontWeight.w600, color: const Color(0xFF212121)),
        titleMedium: GoogleFonts.amiri(fontSize: 14, fontWeight: FontWeight.w500, color: const Color(0xFF212121)),
        titleSmall: GoogleFonts.amiri(fontSize: 12, fontWeight: FontWeight.w500, color: const Color(0xFF212121)),
        bodyLarge: GoogleFonts.amiri(fontSize: 16, color: const Color(0xFF212121)),
        bodyMedium: GoogleFonts.amiri(fontSize: 14, color: const Color(0xFF212121)),
        bodySmall: GoogleFonts.amiri(fontSize: 12, color: const Color(0xFF212121)),
        labelLarge: GoogleFonts.amiri(fontSize: 14, fontWeight: FontWeight.w500, color: const Color(0xFF212121)),
        labelMedium: GoogleFonts.amiri(fontSize: 12, fontWeight: FontWeight.w500, color: const Color(0xFF212121)),
        labelSmall: GoogleFonts.amiri(fontSize: 10, fontWeight: FontWeight.w500, color: const Color(0xFF212121)),
      ),
    );
  }

  // Dark Theme
  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: ColorScheme.dark(
        primary: primaryColor,
        primaryContainer: primaryColor.withValues(alpha: 0.3),
        secondary: secondaryColor,
        secondaryContainer: secondaryColor.withValues(alpha: 0.3),
        tertiary: accentColor,
        tertiaryContainer: accentColor.withValues(alpha: 0.3),
        surface: const Color(0xFF1E1E1E),
        onPrimary: Colors.white,
        onSecondary: Colors.white,
        onSurface: Colors.white,
        surfaceContainerHighest: const Color(0xFF2C2C2C),
      ),
      scaffoldBackgroundColor: const Color(0xFF121212),
      appBarTheme: AppBarTheme(
        backgroundColor: const Color(0xFF1E1E1E),
        foregroundColor: Colors.white,
        elevation: 0,
        centerTitle: true,
        titleTextStyle: GoogleFonts.amiri(
          fontSize: 20,
          fontWeight: FontWeight.bold,
          color: Colors.white,
        ),
      ),
      cardTheme: CardThemeData(
        color: const Color(0xFF2C2C2C),
        elevation: 2,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primaryColor,
          foregroundColor: Colors.white,
          elevation: 2,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
          textStyle: GoogleFonts.amiri(
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: primaryColor,
          side: const BorderSide(color: primaryColor, width: 2),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
          textStyle: GoogleFonts.amiri(
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFF2C2C2C),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Colors.grey),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Colors.grey),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: primaryColor, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Colors.red, width: 1),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Colors.red, width: 2),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        labelStyle: GoogleFonts.amiri(
          fontSize: 14,
          color: const Color(0xFF9E9E9E),
        ),
        hintStyle: GoogleFonts.amiri(
          fontSize: 14,
          color: const Color(0xFFBDBDBD),
        ),
      ),
      floatingActionButtonTheme: FloatingActionButtonThemeData(
        backgroundColor: primaryColor,
        foregroundColor: Colors.white,
        elevation: 4,
      ),
      dividerTheme: DividerThemeData(
        color: const Color(0xFF424242),
        thickness: 1,
      ),
      textTheme: TextTheme(
        displayLarge: GoogleFonts.amiri(fontSize: 32, fontWeight: FontWeight.bold, color: Colors.white),
        displayMedium: GoogleFonts.amiri(fontSize: 28, fontWeight: FontWeight.bold, color: Colors.white),
        displaySmall: GoogleFonts.amiri(fontSize: 24, fontWeight: FontWeight.bold, color: Colors.white),
        headlineLarge: GoogleFonts.amiri(fontSize: 22, fontWeight: FontWeight.w600, color: Colors.white),
        headlineMedium: GoogleFonts.amiri(fontSize: 20, fontWeight: FontWeight.w600, color: Colors.white),
        headlineSmall: GoogleFonts.amiri(fontSize: 18, fontWeight: FontWeight.w600, color: Colors.white),
        titleLarge: GoogleFonts.amiri(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.white),
        titleMedium: GoogleFonts.amiri(fontSize: 14, fontWeight: FontWeight.w500, color: Colors.white),
        titleSmall: GoogleFonts.amiri(fontSize: 12, fontWeight: FontWeight.w500, color: Colors.white),
        bodyLarge: GoogleFonts.amiri(fontSize: 16, color: Colors.white),
        bodyMedium: GoogleFonts.amiri(fontSize: 14, color: Colors.white),
        bodySmall: GoogleFonts.amiri(fontSize: 12, color: Colors.white),
        labelLarge: GoogleFonts.amiri(fontSize: 14, fontWeight: FontWeight.w500, color: Colors.white),
        labelMedium: GoogleFonts.amiri(fontSize: 12, fontWeight: FontWeight.w500, color: Colors.white),
        labelSmall: GoogleFonts.amiri(fontSize: 10, fontWeight: FontWeight.w500, color: Colors.white),
      ),
    );
  }
}
