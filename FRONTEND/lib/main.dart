import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';
import 'login_screen.dart';
import 'main_screen.dart';
import 'report_screen.dart';

void main() {
  runApp(MyApp());
}

class MyApp extends StatelessWidget {
  MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (context) => ClosetProvider(),
      child: MaterialApp(
        title: 'EcoLabel',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFF4A4EFE),
          ),
          useMaterial3: true,
        ),
        initialRoute: '/login',
        routes: {
          '/login': (context) => LoginScreen(),
          '/main': (context) => MainScreen(),
          '/report': (context) => Scaffold(
            appBar: AppBar(title: const Text('상세 리포트')),
            body: ReportScreen(),
          ),
        },
      ),
    );
  }
}