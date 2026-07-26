"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { supabase } from "@/utils/supabase/client";
import { BrainCircuit, Loader2, ArrowRight, ArrowLeft, CheckCircle2, Copy } from "lucide-react";
import Link from "next/link";
import axios from "axios";

const API_BASE = "http://127.0.0.1:8000/api/v1";

interface QuizQuestion {
  question: string;
  options: string[];
  correct_answer: string;
  explanation: string;
  difficulty: string;
  source_chunk: number;
}

interface QuizData {
  id: string;
  filename: string;
  total_questions: number;
  created_at: string;
  llm_model: string;
  questions: QuizQuestion[];
}

export default function QuizInterface() {
  const params = useParams();
  const quizId = params.id as string;
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [quiz, setQuiz] = useState<QuizData | null>(null);
  
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});

  useEffect(() => {
    const fetchQuiz = async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) {
        router.push("/");
        return;
      }

      try {
        const res = await axios.get(`${API_BASE}/quizzes/${quizId}`, {
          headers: { Authorization: `Bearer ${session.access_token}` }
        });
        setQuiz(res.data);
      } catch (err: any) {
        setError("Failed to load quiz. It may not exist or you don't have access.");
      } finally {
        setLoading(false);
      }
    };
    fetchQuiz();
  }, [quizId, router]);

  const handleSelectOption = (option: string) => {
    setAnswers({ ...answers, [currentIndex]: option });
  };

  const handleNext = () => {
    if (quiz && currentIndex < quiz.questions.length - 1) {
      setCurrentIndex(currentIndex + 1);
    }
  };

  const handlePrev = () => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
    }
  };

  const handleSubmit = () => {
    // Save answers to session storage for the results page
    sessionStorage.setItem(`quiz_answers_${quizId}`, JSON.stringify(answers));
    sessionStorage.setItem(`quiz_data_${quizId}`, JSON.stringify(quiz));
    router.push(`/results/${quizId}`);
  };

  const [copied, setCopied] = useState(false);

  const handleCopyQuiz = async () => {
    if (!quiz) return;
    
    let textToCopy = `Quiz: ${quiz.filename}\n\n`;
    
    quiz.questions.forEach((q, idx) => {
      textToCopy += `Q${idx + 1}: ${q.question}\n`;
      q.options.forEach((opt, oIdx) => {
        const letter = String.fromCharCode(65 + oIdx);
        textToCopy += `${letter}) ${opt}\n`;
      });
      textToCopy += `Answer: ${q.correct_answer}\n`;
      textToCopy += `Explanation: ${q.explanation}\n\n`;
    });

    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy text: ", err);
    }
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50 dark:bg-slate-950">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (error || !quiz || quiz.questions.length === 0) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-slate-50 dark:bg-slate-950 px-4 text-center">
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-red-800 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-200">
          <p className="font-medium mb-4">{error || "No questions found for this quiz."}</p>
          <Link href="/dashboard" className="text-indigo-600 hover:underline dark:text-indigo-400">
            Return to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  const currentQuestion = quiz.questions[currentIndex];
  const selectedAnswer = answers[currentIndex];
  const progress = Math.round((Object.keys(answers).length / quiz.questions.length) * 100);

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-50">
      
      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b border-slate-200/50 dark:border-slate-800/50 bg-white/50 dark:bg-slate-950/50 backdrop-blur-xl">
        <div className="container mx-auto flex h-16 items-center justify-between px-4 md:px-6">
          <Link href="/dashboard" className="flex items-center gap-2 font-bold tracking-tight text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100 transition-colors">
            <ArrowLeft className="h-5 w-5" />
            Exit Quiz
          </Link>
          <div className="flex items-center gap-4 font-semibold">
            <button
              onClick={handleCopyQuiz}
              className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300 dark:hover:bg-slate-900 dark:hover:text-slate-50"
              title="Copy all questions and answers"
            >
              {copied ? (
                <>
                  <CheckCircle2 className="mr-2 h-4 w-4 text-green-500" />
                  Copied!
                </>
              ) : (
                <>
                  <Copy className="mr-2 h-4 w-4" />
                  Copy Quiz
                </>
              )}
            </button>
            <div className="hidden sm:flex items-center gap-2">
              <BrainCircuit className="h-5 w-5 text-indigo-600" />
              <span className="truncate max-w-[200px]">{quiz.filename}</span>
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 container mx-auto px-4 py-8 md:py-12 md:px-6 max-w-3xl flex flex-col">
        
        {/* Progress Bar */}
        <div className="mb-8">
          <div className="flex justify-between text-sm font-medium text-slate-500 mb-2 dark:text-slate-400">
            <span>Question {currentIndex + 1} of {quiz.questions.length}</span>
            <span>{progress}% Completed</span>
          </div>
          <div className="h-2 w-full rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
            <div 
              className="h-full bg-indigo-600 transition-all duration-300 ease-out"
              style={{ width: `${((currentIndex + 1) / quiz.questions.length) * 100}%` }}
            />
          </div>
        </div>

        {/* Question Card */}
        <div className="flex-1">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-10 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            
            <div className="mb-8">
              <span className="inline-flex items-center rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700 ring-1 ring-inset ring-indigo-600/20 dark:bg-indigo-900/30 dark:text-indigo-400 dark:ring-indigo-800 mb-4">
                {currentQuestion.difficulty.charAt(0).toUpperCase() + currentQuestion.difficulty.slice(1)} Difficulty
              </span>
              <h2 className="text-xl sm:text-2xl font-bold leading-relaxed">
                {currentQuestion.question}
              </h2>
            </div>

            <div className="space-y-3">
              {currentQuestion.options.map((option, idx) => {
                const isSelected = selectedAnswer === option;
                return (
                  <button
                    key={idx}
                    onClick={() => handleSelectOption(option)}
                    className={`w-full flex items-center justify-between rounded-xl border p-4 text-left transition-all ${
                      isSelected 
                        ? "border-indigo-600 bg-indigo-50 ring-1 ring-indigo-600 dark:border-indigo-500 dark:bg-indigo-900/20 dark:ring-indigo-500" 
                        : "border-slate-200 bg-white hover:border-indigo-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:hover:border-indigo-700 dark:hover:bg-slate-900"
                    }`}
                  >
                    <span className={`font-medium ${isSelected ? "text-indigo-900 dark:text-indigo-100" : "text-slate-700 dark:text-slate-300"}`}>
                      {option}
                    </span>
                    {isSelected && (
                      <CheckCircle2 className="h-5 w-5 text-indigo-600 dark:text-indigo-400 shrink-0 ml-4" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Navigation Controls */}
        <div className="mt-8 flex items-center justify-between border-t border-slate-200 pt-6 dark:border-slate-800">
          <button
            onClick={handlePrev}
            disabled={currentIndex === 0}
            className="inline-flex h-12 items-center justify-center rounded-xl px-6 text-sm font-medium transition-colors hover:bg-slate-100 disabled:pointer-events-none disabled:opacity-50 dark:hover:bg-slate-800"
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Previous
          </button>

          {currentIndex === quiz.questions.length - 1 ? (
            <button
              onClick={handleSubmit}
              disabled={Object.keys(answers).length !== quiz.questions.length}
              className="inline-flex h-12 items-center justify-center rounded-xl bg-green-600 px-8 text-base font-semibold text-white shadow-sm transition-all hover:bg-green-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-600 disabled:pointer-events-none disabled:opacity-50"
            >
              Submit Quiz
            </button>
          ) : (
            <button
              onClick={handleNext}
              className="inline-flex h-12 items-center justify-center rounded-xl bg-indigo-600 px-8 text-base font-semibold text-white shadow-sm transition-all hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600"
            >
              Next <ArrowRight className="ml-2 h-4 w-4" />
            </button>
          )}
        </div>
      </main>
    </div>
  );
}
