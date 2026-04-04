import 'package:flutter/material.dart';
import 'main_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  // true면 로그인 화면, false면 회원가입 화면
  bool isLogin = true;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // 배경색 (아주 연한 파란빛/회색빛)
      backgroundColor: const Color(0xFFF4F7FF),
      body: Center(
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.all(24.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // 1. 상단 로고 및 타이틀
                _buildHeader(),
                const SizedBox(height: 32),

                // 2. 메인 카드 (입력창 묶음)
                Container(
                  width: double.infinity,
                  constraints: const BoxConstraints(maxWidth: 400), // 웹/PC에서도 예쁘게 보이도록 최대 너비 제한
                  padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(16),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.05),
                        blurRadius: 20,
                        offset: const Offset(0, 10),
                      ),
                    ],
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // 토글 버튼 (로그인 / 회원가입)
                      _buildToggleButtons(),
                      const SizedBox(height: 24),

                      // 이름 입력창 (회원가입일 때만 보임)
                      if (!isLogin) ...[
                        _buildTextField(label: '이름', hint: '홍길동', icon: Icons.person_outline),
                        const SizedBox(height: 16),
                      ],

                      // 이메일 입력창
                      _buildTextField(label: '이메일', hint: 'example@email.com', icon: Icons.mail_outline),
                      const SizedBox(height: 16),

                      // 비밀번호 입력창
                      _buildTextField(
                        label: '비밀번호',
                        hint: '최소 6자 이상',
                        icon: Icons.lock_outline,
                        isPassword: true,
                      ),
                      const SizedBox(height: 24),

                      // 메인 버튼 (로그인/회원가입)
                      SizedBox(
                        width: double.infinity,
                        height: 50,
                        child: ElevatedButton(
                          onPressed: () {
                            Navigator.pushReplacementNamed(context, '/main');
                          },
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF4A4EFE), // 버튼 색상
                            foregroundColor: Colors.white,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            elevation: 0,
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(
                                isLogin ? '로그인' : '회원가입',
                                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                              ),
                              const SizedBox(width: 8),
                              const Icon(Icons.arrow_forward, size: 20),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 24),

                      // 하단 텍스트 버튼
                      Center(
                        child: TextButton(
                          onPressed: () {
                            setState(() {
                              isLogin = !isLogin; // 탭 전환
                            });
                          },
                          child: RichText(
                            text: TextSpan(
                              text: isLogin ? '계정이 없으신가요? ' : '이미 계정이 있으신가요? ',
                              style: const TextStyle(color: Colors.grey, fontSize: 14),
                              children: [
                                TextSpan(
                                  text: isLogin ? '회원가입하기' : '로그인하기',
                                  style: const TextStyle(
                                    color: Color(0xFF4A4EFE),
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  // 상단 로고 위젯
  Widget _buildHeader() {
    return Column(
      children: [
        Container(
          width: 60,
          height: 60,
          decoration: const BoxDecoration(
            color: Color(0xFF4A4EFE),
            shape: BoxShape.circle,
          ),
          child: const Icon(Icons.eco_outlined, color: Colors.white, size: 32),
        ),
        const SizedBox(height: 16),
        const Text(
          'EcoLabel',
          style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: Color(0xFF1A1A1A)),
        ),
        const SizedBox(height: 8),
        const Text(
          '지속 가능한 옷 관리 시작하기',
          style: TextStyle(fontSize: 14, color: Colors.grey),
        ),
      ],
    );
  }

  // 토글 버튼 위젯 (로그인 / 회원가입)
  Widget _buildToggleButtons() {
    return Container(
      height: 48,
      decoration: BoxDecoration(
        color: const Color(0xFFF4F5F9), // 옅은 회색 배경
        borderRadius: BorderRadius.circular(8),
      ),
      padding: const EdgeInsets.all(4),
      child: Row(
        children: [
          Expanded(
            child: GestureDetector(
              onTap: () => setState(() => isLogin = true),
              child: Container(
                decoration: BoxDecoration(
                  color: isLogin ? Colors.white : Colors.transparent,
                  borderRadius: BorderRadius.circular(6),
                  boxShadow: isLogin
                      ? [BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 4)]
                      : [],
                ),
                alignment: Alignment.center,
                child: Text(
                  '로그인',
                  style: TextStyle(
                    fontWeight: isLogin ? FontWeight.bold : FontWeight.normal,
                    color: isLogin ? Colors.blueAccent : Colors.grey,
                  ),
                ),
              ),
            ),
          ),
          Expanded(
            child: GestureDetector(
              onTap: () => setState(() => isLogin = false),
              child: Container(
                decoration: BoxDecoration(
                  color: !isLogin ? Colors.white : Colors.transparent,
                  borderRadius: BorderRadius.circular(6),
                  boxShadow: !isLogin
                      ? [
                    BoxShadow(
                        color: Colors.black.withOpacity(0.05), blurRadius: 4, offset: const Offset(0, 2))
                  ]
                      : [],
                ),
                alignment: Alignment.center,
                child: Text(
                  '회원가입',
                  style: TextStyle(
                    fontWeight: !isLogin ? FontWeight.bold : FontWeight.normal,
                    color: !isLogin ? Colors.blueAccent : Colors.grey,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // 텍스트 입력창 공통 위젯
  Widget _buildTextField({
    required String label,
    required String hint,
    required IconData icon,
    bool isPassword = false,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: Color(0xFF4A4A4A)),
        ),
        const SizedBox(height: 8),
        TextField(
          obscureText: isPassword,
          decoration: InputDecoration(
            hintText: hint,
            hintStyle: const TextStyle(color: Colors.grey),
            prefixIcon: Icon(icon, color: Colors.grey),
            suffixIcon: isPassword ? const Icon(Icons.visibility_outlined, color: Colors.grey) : null,
            filled: true,
            fillColor: Colors.white,
            contentPadding: const EdgeInsets.symmetric(vertical: 16),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: BorderSide(color: Colors.grey.shade300),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: const BorderSide(color: Color(0xFF4A4EFE), width: 2),
            ),
          ),
        ),
      ],
    );
  }
}