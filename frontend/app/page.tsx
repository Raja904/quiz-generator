"use client";

import { ArrowRight, BookOpen, BrainCircuit, Sparkles, Upload, Loader2 } from "lucide-react";
import { useState } from "react";
import { supabase } from "@/utils/supabase/client";

export default function Home() {
  const [loading, setLoading] = useState(false);

  const handleSignIn = async () => {
    setLoading(true);
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/dashboard`,
      },
    });
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900 font-sans">

      {/* Navbar */}
      <header className="sticky top-0 z-50 w-full border-b border-slate-200 bg-white/80 backdrop-blur-xl">
        <div className="container mx-auto flex h-16 items-center justify-between px-4 md:px-6">
          <div className="flex items-center gap-2 font-bold text-xl tracking-tight">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white">
              <BrainCircuit className="h-5 w-5" />
            </div>
            QuizGenius
          </div>
          <nav>
            <button
              onClick={handleSignIn}
              disabled={loading}
              className="inline-flex h-9 items-center justify-center rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow transition-colors hover:bg-slate-700 disabled:opacity-50"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Get Started"}
            </button>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        {/* Hero Section */}
        <section className="relative overflow-hidden py-24 lg:py-32">
          <div className="absolute inset-0 -z-10" style={{background: "radial-gradient(ellipse at top, #e0e7ff 0%, #f8fafc 60%)"}}></div>

          <div className="container mx-auto px-4 md:px-6">
            <div className="flex flex-col items-center text-center space-y-8">

              <div className="inline-flex items-center rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-sm font-medium text-indigo-800">
                <Sparkles className="mr-2 h-4 w-4" />
                Turn your study materials into interactive quizzes
              </div>

              <h1 className="max-w-4xl text-4xl font-extrabold tracking-tight sm:text-5xl md:text-6xl lg:text-7xl">
                Master your PDFs with{" "}
                <span className="text-indigo-600">AI-Generated Quizzes</span>
              </h1>

              <p className="max-w-2xl text-lg leading-relaxed text-slate-600">
                Upload your lecture slides, notes, or textbooks and let our AI instantly create personalized quizzes to test your knowledge and improve retention.
              </p>

              <div className="flex flex-col sm:flex-row gap-4 mt-8">
                <button
                  onClick={handleSignIn}
                  disabled={loading}
                  className="inline-flex h-12 items-center justify-center rounded-full bg-indigo-600 px-8 text-base font-semibold text-white shadow-lg transition-all hover:bg-indigo-700 disabled:opacity-70"
                >
                  {loading ? (
                    <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  ) : (
                    <>
                      Sign in with Google
                      <ArrowRight className="ml-2 h-4 w-4" />
                    </>
                  )}
                </button>
                <a
                  href="#how-it-works"
                  className="inline-flex h-12 items-center justify-center rounded-full border border-slate-200 bg-white px-8 text-base font-medium text-slate-900 shadow-sm transition-colors hover:bg-slate-100"
                >
                  How it works
                </a>
              </div>
            </div>
          </div>
        </section>

        {/* How it works */}
        <section id="how-it-works" className="py-24 bg-white">
          <div className="container mx-auto px-4 md:px-6">
            <div className="text-center mb-16">
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">From PDF to Quiz in seconds</h2>
              <p className="mt-4 text-lg text-slate-600">Our seamless process gets you studying faster.</p>
            </div>

            <div className="grid gap-12 md:grid-cols-3">
              <div className="flex flex-col items-center text-center space-y-4">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-100 text-indigo-600">
                  <Upload className="h-8 w-8" />
                </div>
                <h3 className="text-xl font-bold">1. Upload PDF</h3>
                <p className="text-slate-600">Simply drag and drop your study materials. We support class notes, textbooks, and slide decks.</p>
              </div>

              <div className="flex flex-col items-center text-center space-y-4">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-100 text-blue-600">
                  <BrainCircuit className="h-8 w-8" />
                </div>
                <h3 className="text-xl font-bold">2. AI Analysis</h3>
                <p className="text-slate-600">Our advanced AI extracts the most important concepts and formulates challenging questions.</p>
              </div>

              <div className="flex flex-col items-center text-center space-y-4">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-purple-100 text-purple-600">
                  <BookOpen className="h-8 w-8" />
                </div>
                <h3 className="text-xl font-bold">3. Start Studying</h3>
                <p className="text-slate-600">Take your personalized quiz, review explanations, and master your coursework efficiently.</p>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 py-8 bg-slate-50">
        <div className="container mx-auto px-4 md:px-6 flex flex-col items-center justify-between gap-4 md:flex-row">
          <div className="flex items-center gap-2 font-semibold">
            <BrainCircuit className="h-5 w-5 text-indigo-600" />
            <span>QuizGenius</span>
          </div>
          <p className="text-sm text-slate-500">
            &copy; {new Date().getFullYear()} QuizGenius. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
