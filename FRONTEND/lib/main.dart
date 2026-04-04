import 'package:flutter/material.dart';
import 'login_screen.dart';
import 'main_screen.dart';
import 'report_screen.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    // 앱 전체에 ClosetProvider 보관소를 제공합니다!
    return ChangeNotifierProvider(
      create: (context) => ClosetProvider(),
      child: MaterialApp(
        title: 'EcoLabel',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF4A4EFE)),
          useMaterial3: true,
        ),
        initialRoute: '/login',
        routes: {
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