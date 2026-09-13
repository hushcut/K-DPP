// 앱 시작 준비, 전역 상태 등록, 테마와 이름 기반 라우트를 구성하는 진입 파일입니다.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';
import 'login_screen.dart';
import 'main_screen.dart';
import 'splash_screen.dart';
import 'email_login_screen.dart';
import 'signup_screen.dart';
import 'settings_screen.dart';
import 'theme/app_palette.dart';
import 'theme_provider.dart';
import 'display_settings_screen.dart';

/// Flutter 바인딩과 화면 방향을 설정한 뒤 앱 전역 Provider를 주입합니다.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);

  final closetProvider = ClosetProvider();
  final themeProvider = ThemeProvider();
  await themeProvider.loadThemeMode();

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: closetProvider),
        ChangeNotifierProvider.value(value: themeProvider),
      ],
      child: const MyApp(),
    ),
  );
}

/// 현재 테마 설정을 반영해 K-DPP의 최상위 [MaterialApp]을 구성합니다.
class MyApp extends StatelessWidget {
  const MyApp({super.key});

  ThemeData _lightTheme() {
    return ThemeData(
      brightness: Brightness.light,
      scaffoldBackgroundColor: const Color(0xFFF8F9FC),
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppPalette.accent,
        brightness: Brightness.light,
      ),
      useMaterial3: true,
    );
  }

  ThemeData _darkTheme() {
    return ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: const Color(0xFF121212),
      canvasColor: const Color(0xFF121212),
      cardColor: const Color(0xFF1C1C1E),
      dividerColor: const Color(0xFF2C2C2E),
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppPalette.accent,
        brightness: Brightness.dark,
        surface: const Color(0xFF1C1C1E),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: Color(0xFF121212),
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        iconTheme: IconThemeData(color: Colors.white),
        titleTextStyle: TextStyle(
          color: Colors.white,
          fontSize: 20,
          fontWeight: FontWeight.w700,
        ),
      ),
      dialogTheme: const DialogThemeData(
        backgroundColor: Color(0xFF1C1C1E),
        titleTextStyle: TextStyle(
          color: Colors.white,
          fontSize: 18,
          fontWeight: FontWeight.w700,
        ),
        contentTextStyle: TextStyle(
          color: Color(0xFFD1D1D6),
          fontSize: 14,
          height: 1.5,
        ),
      ),
      navigationBarTheme: const NavigationBarThemeData(
        backgroundColor: Color(0xFF161616),
        indicatorColor: Color(0xFF2A2A2E),
        labelTextStyle: WidgetStatePropertyAll(
          TextStyle(
            color: Colors.white,
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      useMaterial3: true,
    );
  }

  @override
  Widget build(BuildContext context) {
    // ThemeProvider가 알림을 보내면 MaterialApp의 themeMode도 즉시 갱신됩니다.
    return Consumer<ThemeProvider>(
      builder: (context, themeProvider, child) {
        return MaterialApp(
          title: 'K-DPP',
          debugShowCheckedModeBanner: false,
          theme: _lightTheme(),
          darkTheme: _darkTheme(),
          themeMode: themeProvider.themeMode,
          initialRoute: '/splash',
          // 스플래시부터 인증 화면과 메인 화면까지 앱의 주요 이동 경로입니다.
          routes: {
            '/splash': (context) => const SplashScreen(),
            '/login': (context) => const LoginScreen(),
            '/email-login': (context) => const EmailLoginScreen(),
            '/signup': (context) => const SignupScreen(),
            '/settings': (context) => const SettingsScreen(),
            '/display-settings': (context) => const DisplaySettingsScreen(),
            '/main': (context) => const MainScreen(),
          },
        );
      },
    );
  }
}
