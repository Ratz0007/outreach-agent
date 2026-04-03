"use client";

import React, { useState, useEffect, useRef } from 'react';
import { 
  Sparkles, 
  Mic, 
  X, 
  Send, 
  Bot, 
  User, 
  Loader2, 
  Volume2, 
  VolumeX,
  PlayCircle,
  Command,
  ChevronRight,
  Maximize2,
  Minimize2,
  CheckCircle2
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import { motion, AnimatePresence } from 'framer-motion';

export function CoachWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [messages, setMessages] = useState<any[]>([
    { role: 'assistant', content: "Hello! I'm your AI Career Coach. How can I help you accelerate your job search today?" }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Web Speech API
  const [recognition, setRecognition] = useState<any>(null);

  useEffect(() => {
    if (typeof window !== 'undefined' && ('WebkitSpeechRecognition' in window || 'speechRecognition' in window)) {
      const SpeechRecognition = (window as any).WebkitSpeechRecognition || (window as any).speechRecognition;
      const rec = new SpeechRecognition();
      rec.continuous = false;
      rec.interimResults = false;
      rec.lang = 'en-US';

      rec.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        setInput(transcript);
        setIsRecording(false);
        handleSend(transcript);
      };

      rec.onerror = () => setIsRecording(false);
      rec.onend = () => setIsRecording(false);

      setRecognition(rec);
    }
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const toggleRecording = () => {
    if (isRecording) {
      recognition?.stop();
    } else {
      setIsRecording(true);
      recognition?.start();
    }
  };

  const handleSend = async (text = input) => {
    if (!text.trim()) return;
    
    const userMsg = { role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await api.coach.chat(text, false);
      setMessages(prev => [...prev, { role: 'assistant', content: res.response, actions: res.actions_taken }]);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: "Sorry, I had a connection issue. Can you try again?" }]);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return (
    <motion.button
      layoutId="coach-widget"
      onClick={() => setIsOpen(true)}
      className="fixed bottom-8 right-8 w-16 h-16 rounded-3xl bg-primary text-primary-foreground shadow-2xl shadow-primary/40 flex items-center justify-center group hover:scale-110 transition-all z-50 overflow-hidden"
    >
      <div className="absolute inset-0 bg-gradient-to-tr from-indigo-600 to-purple-600 animate-pulse opacity-0 group-hover:opacity-100 transition-opacity" />
      <Sparkles className="w-8 h-8 relative z-10" />
      <div className="absolute -top-1 -right-1 w-4 h-4 bg-emerald-500 rounded-full border-2 border-background animate-bounce" />
    </motion.button>
  );

  return (
    <AnimatePresence>
      <motion.div 
        layoutId="coach-widget"
        className={cn(
          "fixed bottom-8 right-8 bg-background border shadow-2xl rounded-[32px] overflow-hidden flex flex-col z-50 transition-all duration-300",
          isMinimized ? "w-72 h-16" : "w-[400px] h-[600px]"
        )}
      >
        {/* Header */}
        <div className="h-16 bg-gradient-to-r from-indigo-500 to-purple-600 px-5 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
             <div className="w-8 h-8 rounded-xl bg-white/20 flex items-center justify-center">
                <Bot className="w-5 h-5 text-white" />
             </div>
             <div className="text-white">
                <p className="text-sm font-bold leading-none">Career Coach</p>
                <p className="text-[10px] opacity-80 font-medium">Agent Active</p>
             </div>
          </div>
          <div className="flex items-center gap-1">
             <button onClick={() => setIsMinimized(!isMinimized)} className="p-2 hover:bg-white/10 rounded-lg text-white">
                {isMinimized ? <Maximize2 className="w-4 h-4" /> : <Minimize2 className="w-4 h-4" />}
             </button>
             <button onClick={() => setIsOpen(false)} className="p-2 hover:bg-white/10 rounded-lg text-white">
                <X className="w-4 h-4" />
             </button>
          </div>
        </div>

        {!isMinimized && (
          <>
            {/* Messages Area */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto p-5 space-y-4 custom-scrollbar">
              {messages.map((msg, i) => (
                <div key={i} className={cn(
                  "flex flex-col gap-2 max-w-[85%]",
                  msg.role === 'user' ? "ml-auto items-end" : "mr-auto items-start"
                )}>
                  <div className={cn(
                    "p-4 rounded-3xl text-sm leading-relaxed",
                    msg.role === 'user' ? "bg-primary text-primary-foreground rounded-tr-none" : "bg-muted/50 rounded-tl-none border"
                  )}>
                    {msg.content}
                  </div>
                  {msg.actions && msg.actions.length > 0 && (
                    <div className="p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-2xl border border-emerald-100 dark:border-emerald-800 text-[10px] font-bold text-emerald-600 flex items-center gap-2">
                       <CheckCircle2 className="w-3 h-3" /> ACTION COMPLETED
                    </div>
                  )}
                  {msg.role === 'assistant' && i === messages.length - 1 && !loading && (
                    <div className="flex gap-2 mt-1">
                       <button className="text-[10px] bg-muted px-2 py-1 rounded-lg hover:bg-primary/10 hover:text-primary font-bold">Source Jobs</button>
                       <button className="text-[10px] bg-muted px-2 py-1 rounded-lg hover:bg-primary/10 hover:text-primary font-bold">View Pipeline</button>
                    </div>
                  )}
                </div>
              ))}
              {loading && (
                <div className="flex items-start gap-2 max-w-[85%] animate-pulse">
                   <div className="w-10 h-10 rounded-2xl bg-muted flex items-center justify-center">
                      <Loader2 className="w-5 h-5 animate-spin" />
                   </div>
                </div>
              )}
            </div>

            {/* Input Area */}
            <div className="p-4 bg-muted/20 border-t">
              <div className="flex items-center gap-2 bg-background border rounded-[28px] p-2 pl-4 shadow-sm focus-within:ring-2 focus-within:ring-primary/20 transition-all">
                <input 
                  type="text" 
                  placeholder="Ask your coach anything..." 
                  className="flex-1 text-sm bg-transparent border-none outline-none"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSend()}
                />
                <Button 
                  variant="ghost" 
                  size="icon" 
                  onClick={toggleRecording}
                  className={cn(
                    "rounded-full w-10 h-10 transition-all",
                    isRecording ? "bg-destructive/10 text-destructive animate-pulse" : "hover:bg-primary/10"
                  )}
                >
                  <Mic className={cn("w-5 h-5", isRecording ? "fill-destructive" : "")} />
                </Button>
                <Button 
                  size="icon" 
                  onClick={() => handleSend()}
                  disabled={!input.trim()}
                  className="rounded-full w-10 h-10 shadow-lg shadow-primary/20"
                >
                  <Send className="w-4 h-4" />
                </Button>
              </div>
              <div className="mt-3 flex items-center justify-between px-2">
                 <div className="flex items-center gap-2 text-[10px] text-muted-foreground font-bold tracking-widest uppercase">
                    <Command className="w-3 h-3" /> Dictate 100/100
                 </div>
                 <div className="flex gap-2">
                    <Volume2 className="w-3 h-3 text-muted-foreground" />
                 </div>
              </div>
            </div>
          </>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
