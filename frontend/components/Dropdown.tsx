import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export default function Dropdown({ onSelect }: { onSelect: (name: string) => void }) {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedPerson, setSelectedPerson] = useState("Ram");
  const people = ["Ram", "Shyam", "Ketan"];

  return (
    <div className="relative w-64 mx-auto mt-6">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full bg-gradient-to-r from-gray-800 to-gray-900 text-white py-3 px-5 rounded-lg shadow-md flex justify-between items-center border border-gray-700 hover:bg-gray-700 transition-all"
      >
        <span className="font-medium text-lg">{selectedPerson}</span>
        <motion.div animate={{ rotate: isOpen ? 180 : 0 }}>
          <ChevronDown className="h-5 w-5" />
        </motion.div>
      </button>
      <AnimatePresence>
        {isOpen && (
          <motion.ul
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            transition={{ duration: 0.2 }}
            className="absolute mt-2 w-full bg-gray-800 text-white shadow-lg rounded-lg border border-gray-700 overflow-hidden"
          >
            {people.map((person, index) => (
              <motion.li
                key={index}
                onClick={() => {
                  setSelectedPerson(person);
                  setIsOpen(false);
                  onSelect(person);
                }}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="cursor-pointer select-none py-3 px-5 transition-all hover:bg-gray-700 text-lg"
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
