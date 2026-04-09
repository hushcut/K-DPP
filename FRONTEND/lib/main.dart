import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';
import 'login_screen.dart';
import 'main_screen.dart';
import 'report_screen.dart';
import 'splash_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final closetProvider = ClosetProvider();

  runApp(MyApp(closetProvider: closetProvider));
}

class MyApp extends StatelessWidget {
  final ClosetProvider closetProvider;

  const MyApp({
    super.key,
    required this.closetProvider,
  });

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider.value(
      value: closetProvider,
      child: MaterialApp(
        title: 'EcoLabel',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFF4A4EFE),
          ),
          useMaterial3: true,
        ),
        initialRoute: '/splash',
        routes: {
          '/splash': (context) => const SplashScreen(),
          '/login': (context) => const LoginScreen(),
          '/main': (context) => const MainScreen(),
          '/report': (context) => Scaffold(
            appBar: AppBar(title: const Text('상세 리포트')),
            body: const ReportScreen(),
          ),
        },
      ),
    );
  }
}