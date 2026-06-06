import 'package:flutter/material.dart';

class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final backgroundColor = isDark
        ? const Color(0xFF121212)
        : const Color(0xFFF8F9FC);
    final primaryText = isDark ? Colors.white : const Color(0xFF1A1A1A);
    final secondaryText = isDark ? const Color(0xFFD1D1D6) : Colors.grey;
    final subText = isDark ? const Color(0xFFB8B8BE) : const Color(0xFF9A9A9A);

    return Scaffold(
      backgroundColor: backgroundColor,
      body: SafeArea(
        child: Stack(
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Column(
                children: [
                  const Spacer(flex: 2),

                  Container(
                    width: 96,
                    height: 96,
                    decoration: BoxDecoration(
                      color: const Color(0xFF4A4EFE),
                      borderRadius: BorderRadius.circular(28),
                    ),
                    child: const Icon(
                      Icons.eco_outlined,
                      color: Colors.white,
                      size: 46,
                    ),
                  ),
                  const SizedBox(height: 24),

                  Text(
                    'K-DPP',
                    style: TextStyle(
                      fontSize: 30,
                      fontWeight: FontWeight.bold,
                      color: primaryText,
                    ),
                  ),
                  const SizedBox(height: 12),

                  Text(
                    '의류를 더 오래, 더 바르게 관리하세요',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 16,
                      color: secondaryText,
                      height: 1.5,
                    ),
                  ),
                  const SizedBox(height: 8),

                  Text(
                    '라벨 스캔으로 의류 상태와 관리 정보를\n쉽게 확인할 수 있어요.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 14,
                      color: secondaryText,
                      height: 1.5,
                    ),
                  ),

                  const Spacer(flex: 3),

                  Padding(
                    padding: const EdgeInsets.only(bottom: 28),
                    child: Column(
                      children: [
                        SizedBox(
                          width: double.infinity,
                          height: 56,
                          child: ElevatedButton(
                            onPressed: () {
                              Navigator.pushNamed(context, '/email-login');
                            },
                            style: ElevatedButton.styleFrom(
                              elevation: 0,
                              backgroundColor: const Color(0xFF4A4EFE),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(16),
                              ),
                            ),
                            child: const Text(
                              '로그인',
                              style: TextStyle(
                                fontSize: 16,
                                color: Colors.white,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(height: 10),
                        TextButton(
                          onPressed: () {
                            Navigator.pushNamed(context, '/signup');
                          },
                          style: TextButton.styleFrom(
                            padding: const EdgeInsets.symmetric(vertical: 6),
                          ),
                          child: Text(
                            '계정이 없으신가요? 회원가입',
                            style: TextStyle(
                              fontSize: 14,
                              color: subText,
                              decoration: TextDecoration.underline,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
