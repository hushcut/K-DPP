import 'package:flutter/material.dart';
import 'home_screen.dart';
import 'scan_screen.dart';
import 'report_screen.dart';
import 'closet_screen.dart';

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  // 현재 선택된 탭의 인덱스 (0: 홈, 1: 스캔, 2: 리포트, 3: 옷장)
  int _selectedIndex = 0;

  // 4개의 탭에 들어갈 각각의 화면들 (임시로 텍스트만 띄워둡니다)
  final List<Widget> _screens = [
    const HomeScreen(),
    const ScanScreen(),
    const ReportScreen(),
    const ClosetScreen(),
  ];

  // 하단 탭을 눌렀을 때 실행되는 함수
  void _onItemTapped(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('K-DPP', style: TextStyle(fontWeight: FontWeight.bold)),
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        elevation: 0,
        centerTitle: true,
      ),
      body: _screens[_selectedIndex], // 현재 선택된 인덱스에 맞는 화면 보여주기
      bottomNavigationBar: BottomNavigationBar(
        type: BottomNavigationBarType.fixed, // 탭이 4개 이상일 때 아이콘이 움직이지 않게 고정
        backgroundColor: Colors.white,
        selectedItemColor: const Color(0xFF4A4EFE), // 선택된 탭은 메인 파란색!
        unselectedItemColor: Colors.grey, // 선택 안 된 탭은 회색
        currentIndex: _selectedIndex,
        onTap: _onItemTapped,
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.home_outlined),
            activeIcon: Icon(Icons.home),
            label: '홈',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.camera_alt_outlined),
            activeIcon: Icon(Icons.camera_alt),
            label: '스캔',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.analytics_outlined),
            activeIcon: Icon(Icons.analytics),
            label: '리포트',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.checkroom_outlined),
            activeIcon: Icon(Icons.checkroom),
            label: '옷장',
          ),
        ],
      ),
    );
  }
}