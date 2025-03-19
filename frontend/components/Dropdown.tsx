import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export default function Dropdown({ onSelect }: { onSelect: (name: string) => void }) {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedPerson, setSelectedPerson] = useState("Ram");
  const people = ["Ram", "Shyam", "Ketan"];

  return (
    <div className="relative w-72 mx-auto mt-10">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full bg-gradient-to-r from-blue-500 to-purple-600 text-white py-4 px-6 rounded-2xl shadow-xl flex justify-between items-center border border-transparent hover:from-blue-600 hover:to-purple-700 focus:outline-none focus:ring-4 focus:ring-purple-300 transition-all"
      >
        <span className="font-semibold text-lg">{selectedPerson}</span>
        <motion.div animate={{ rotate: isOpen ? 180 : 0 }}>
          <ChevronDown className="h-6 w-6" />
        </motion.div>
      </button>
      <AnimatePresence>
        {isOpen && (
          <motion.ul
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            className="absolute mt-2 w-full bg-white/80 backdrop-blur-md shadow-2xl rounded-2xl overflow-hidden border border-gray-300 divide-y divide-gray-200"
          >
            {people.map((person, index) => (
              <motion.li
                key={index}
                onClick={() => {
                  setSelectedPerson(person);
                  setIsOpen(false);
                  onSelect(person); // ✅ Send selection to parent component
                }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="cursor-pointer select-none py-4 px-6 transition-all text-gray-700 hover:bg-purple-500 hover:text-white text-lg"
              >
                {person}
              </motion.li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}
