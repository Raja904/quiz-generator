"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { BrainCircuit, CheckCircle2, XCircle, ArrowRight, Loader2, RefreshCcw } from "lucide-react";
import Link from "next/link";

interface QuizQuestion {
  question: string;
  options: string[];
  correct_answer: string;
  explanation: string;
  difficulty: string;
}

interface QuizData {
  id: string;
  filename: string;
  questions: QuizQuestion[];
}

export default function ResultsPage() {
  const params = useParams();
  const quizId = params.id as string;
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [quiz, setQuiz] = useState<QuizData | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  
  useEffect(() => {
    try {
      const storedAnswers = sessionStorage.getItem(`quiz_answers_${quizId}`);
      const storedQuiz = sessionStorage.getItem(`quiz_data_${quizId}`);
      
      if (storedAnswers && storedQuiz) {
        setAnswers(JSON.parse(storedAnswers));
        setQuiz(JSON.parse(storedQuiz));
      } else {
        // If data is missing, we can't grade it. Go to dashboard.
        router.push("/dashboard");
      }
    } catch (e) {
      router.push("/dashboard");
    } finally {
      setLoading(false);
    }
  }, [quizId, router]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50 dark:bg-slate-950">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (!quiz) return null;

  // Calculate Score
  let correctCount = 0;
  quiz.questions.forEach((q, idx) => {
    if (answers[idx] === q.correct_answer) {
      correctCount++;
    }
  });

  const percentage = Math.round((correctCount / quiz.questions.length) * 100);
  
  let resultMessage = "Good effort!";
  if (percentage >= 90) resultMessage = "Excellent work!";
  else if (percentage >= 70) resultMessage = "Great job!";
  else if (percentage < 50) resultMessage = "Keep practicing!";

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-50">
      
      {/* Header */}
      <header className="w-full border-b border-slate-200/50 dark:border-slate-800/50 bg-white/50 dark:bg-slate-950/50 backdrop-blur-xl">
        <div className="container mx-auto flex h-16 items-center justify-between px-4 md:px-6">
          <Link href="/dashboard" className="flex items-center gap-2 font-bold tracking-tight">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white">
              <BrainCircuit className="h-5 w-5" />
            </div>
            QuizGenius
          </Link>
          <Link 
            href="/dashboard"
            className="text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
          >
            Back to Dashboard
          </Link>
        </div>
      </header>

      <main className="flex-1 container mx-auto px-4 py-8 md:py-12 md:px-6 max-w-4xl">
        
        {/* Score Summary */}
        <div className="mb-12 rounded-3xl border border-slate-200 bg-white p-8 sm:p-12 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <h1 className="text-3xl sm:text-4xl font-extrabold mb-2">{resultMessage}</h1>
          <p className="text-slate-500 dark:text-slate-400 mb-8">You've completed the quiz for <span className="font-medium text-slate-700 dark:text-slate-300">{quiz.filename}</span></p>
          
          <div className="inline-flex flex-col items-center justify-center rounded-full border-8 border-indigo-50 bg-white h-48 w-48 shadow-inner dark:border-indigo-900/20 dark:bg-slate-900 mb-8">
            <span className="text-5xl font-black text-indigo-600 dark:text-indigo-400">{percentage}%</span>
            <span className="text-sm font-medium text-slate-500 mt-1">{correctCount} of {quiz.questions.length} correct</span>
          </div>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link 
              href={`/quiz/${quizId}`}
              className="inline-flex h-12 w-full sm:w-auto items-center justify-center rounded-xl border border-slate-200 bg-white px-8 text-base font-medium text-slate-900 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-200 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-50 dark:hover:bg-slate-800"
            >
              <RefreshCcw className="mr-2 h-4 w-4" />
              Retake Quiz
            </Link>
            <Link 
              href="/dashboard"
              className="inline-flex h-12 w-full sm:w-auto items-center justify-center rounded-xl bg-indigo-600 px-8 text-base font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600"
            >
              Generate Another Quiz <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </div>
        </div>

        {/* Detailed Review */}
        <div className="space-y-6">
          <h2 className="text-2xl font-bold tracking-tight mb-6">Review Answers</h2>
          
          {quiz.questions.map((q, idx) => {
            const userAnswer = answers[idx];
            const isCorrect = userAnswer === q.correct_answer;
            
            return (
              <div 
                key={idx} 
                className={`rounded-2xl border p-6 sm:p-8 transition-colors ${
                  isCorrect 
                    ? "border-green-200 bg-green-50/50 dark:border-green-900/30 dark:bg-green-900/10" 
                    : "border-red-200 bg-red-50/50 dark:border-red-900/30 dark:bg-red-900/10"
                }`}
              >
                <div className="flex items-start gap-4 mb-6">
                  <div className="shrink-0 mt-1">
                    {isCorrect ? (
                      <CheckCircle2 className="h-6 w-6 text-green-600 dark:text-green-400" />
                    ) : (
                      <XCircle className="h-6 w-6 text-red-600 dark:text-red-400" />
                    )}
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold leading-relaxed mb-4">
                      {idx + 1}. {q.question}
                    </h3>
                    
                    <div className="space-y-3">
                      {q.options.map((option, optIdx) => {
                        const isSelected = option === userAnswer;
                        const isActualCorrect = option === q.correct_answer;
                        
                        let optionClass = "border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900 opacity-60";
                        if (isActualCorrect) {
                          optionClass = "border-green-500 bg-green-100/50 text-green-900 font-medium dark:border-green-500/50 dark:bg-green-900/30 dark:text-green-200 ring-1 ring-green-500";
                        } else if (isSelected && !isCorrect) {
                          optionClass = "border-red-300 bg-red-100/50 text-red-900 dark:border-red-500/50 dark:bg-red-900/30 dark:text-red-200 line-through opacity-80";
                        }

                        return (
                          <div 
                            key={optIdx} 
                            className={`flex w-full items-center justify-between rounded-xl border p-4 text-left ${optionClass}`}
                          >
                            <span>{option}</span>
                            {isActualCorrect && <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600 dark:text-green-400" />}
                          </div>
                        );
                      })}
                    </div>

                    <div className="mt-6 rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-950">
                      <h4 className="text-sm font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">Explanation</h4>
                      <p className="text-slate-700 dark:text-slate-300 text-sm leading-relaxed">
                        {q.explanation}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </main>
    </div>
  );
}
