/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect } from 'react';
import { 
  Waves, 
  Droplets, 
  TestTube, 
  CircleDot, 
  Sparkles, 
  Shield, 
  Pause
} from 'lucide-react';
import { motion } from 'motion/react';

type Program = 'SUV' | 'OSMOS' | 'AKTIV_PENA' | 'PENA' | 'NANO' | 'VOSK' | 'PAUZA';

export default function App() {
  const [activeProgram, setActiveProgram] = useState<Program | 'NONE'>('NONE');
  const [timeLeft, setTimeLeft] = useState(370); // 06:10 in seconds
  const [balance, setBalance] = useState(25000);

  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (activeProgram !== 'PAUZA' && activeProgram !== 'NONE' && timeLeft > 0 && balance > 0) {
      timer = setInterval(() => {
        setTimeLeft((prev) => prev - 1);
        setBalance((prev) => Math.max(0, prev - 50)); // Deduct 50 SO'M per second
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [activeProgram, timeLeft, balance]);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const formatBalance = (amount: number) => {
    return amount.toLocaleString('uz-UZ').replace(/,/g, ' ') + " SO'M";
  };

  const programs = [
    { id: 'SUV' as Program, label: 'SUV', icon: Waves, color: 'bg-[#3b82f6]' },
    { id: 'OSMOS' as Program, label: 'OSMOS', icon: Droplets, color: 'bg-[#0ea5e9]' },
    { id: 'AKTIV_PENA' as Program, label: 'AKTIV PENA', icon: TestTube, color: 'bg-[#d946ef]' },
    { id: 'PENA' as Program, label: 'PENA', icon: CircleDot, color: 'bg-[#06b6d4]' },
    { id: 'NANO' as Program, label: 'NANO', icon: Sparkles, color: 'bg-[#6366f1]' },
    { id: 'VOSK' as Program, label: 'VOSK', icon: Shield, color: 'bg-[#f59e0b]' },
  ];

  const isPaused = activeProgram === 'PAUZA';
  const isNone = activeProgram === 'NONE';
  const headerTextColor = isPaused ? 'text-[#ff4d4d]' : 'text-white';

  const addBalance = () => {
    setBalance((prev) => prev + 5000);
  };

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-white font-sans flex flex-col select-none overflow-hidden">
      {/* Header Section */}
      <div className="flex-1 flex flex-col items-center justify-center py-8 px-4 text-center cursor-pointer" onClick={isNone ? addBalance : undefined}>
        {isNone ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex flex-col items-center"
          >
            <div className="text-2xl font-bold text-[#3b82f6] mb-4 tracking-[0.5em] uppercase opacity-80">
              BALANS
            </div>
            <div className="text-[10rem] font-mono font-black leading-none tracking-tighter text-white break-words max-w-full">
              {balance.toLocaleString('uz-UZ').replace(/,/g, ' ')}
            </div>
            <div className="text-[6rem] font-black leading-none tracking-tighter text-[#3b82f6] mt-4">
              SO'M
            </div>
            <div className="mt-8 text-sm text-white/30 animate-bounce">
              PUL KIRITING
            </div>
          </motion.div>
        ) : (
          <motion.div
            key={activeProgram}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col items-center"
          >
            <h1 className={`text-7xl font-black tracking-tighter mb-4 uppercase ${headerTextColor}`}>
              {activeProgram === 'PAUZA' ? 'PAUZA' : activeProgram.replace('_', ' ')}
            </h1>
            <div className={`text-[12rem] font-mono font-black leading-none tracking-tighter ${headerTextColor} ${isPaused ? 'animate-pulse' : ''}`}>
              {formatTime(timeLeft)}
            </div>
          </motion.div>
        )}
      </div>

      {/* Divider */}
      <div className="h-2 bg-white w-full shadow-[0_0_15px_rgba(255,255,255,0.5)]" />

      {/* Controls Grid */}
      <div className="p-4 grid grid-cols-2 gap-4 bg-[#0a0f1e]">
        {programs.map((prog) => (
          <motion.button
            key={prog.id}
            whileTap={{ scale: 0.95 }}
            onClick={() => balance > 0 && setActiveProgram(prog.id)}
            disabled={balance <= 0}
            className={`
              relative h-32 rounded-lg flex items-center justify-between px-6
              ${prog.color} border-b-8 border-black/20 shadow-lg
              ${activeProgram === prog.id ? 'ring-4 ring-white' : ''}
              ${balance <= 0 ? 'opacity-50 grayscale' : ''}
              transition-all duration-200
            `}
          >
            <div className="w-16 h-16 flex items-center justify-center">
              <prog.icon className="w-12 h-12 text-white/90" />
            </div>
            <span className="text-3xl font-black italic tracking-tighter ml-4">
              {prog.label}
            </span>
          </motion.button>
        ))}
      </div>

      {/* Bottom Controls */}
      <div className="p-4 pt-0 bg-[#0a0f1e]">
        {/* Pause Button */}
        <motion.button
          whileTap={{ scale: 0.98 }}
          onClick={() => setActiveProgram('PAUZA')}
          className={`
            w-full h-32 rounded-lg flex items-center justify-center gap-12
            bg-[#ff4d4d] border-b-8 border-black/20 shadow-lg
            ${activeProgram === 'PAUZA' ? 'ring-4 ring-white' : ''}
          `}
        >
          <div className="w-12 h-12 rounded-full bg-white flex items-center justify-center">
            <div className="w-6 h-2 bg-[#ff4d4d] rounded-full" />
          </div>
          
          <span className="text-5xl font-black italic tracking-tighter">
            PAUZA
          </span>

          <div className="w-12 h-12 rounded-full bg-white flex items-center justify-center">
            <div className="w-6 h-2 bg-[#ff4d4d] rounded-full" />
          </div>
        </motion.button>
      </div>
    </div>
  );
}
