import 'package:flutter/material.dart';
import 'login_screen.dart'; // 우리가 만든 로그인 화면 불러오기

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'EcoLabel',
      debugShowCheckedModeBanner: false, // 우측 상단의 거슬리는 'DEBUG' 띠를 없애줍니다
      theme: ThemeData(
        // 메인 색상을 파란색으로 설정
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF4A4EFE)),
        useMaterial3: true,
      ),
      home: const LoginScreen(), // 앱을 켰을 때 가장 먼저 보여줄 화면!
    );
  }
}