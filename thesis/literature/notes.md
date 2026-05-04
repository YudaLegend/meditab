# Models

## Zero shots
gemma3:4b This model cannot even extract teh correct strutured JSON, One of the reasons that i think, is because the maximum token consumed by this model is aprox 128k token, so once the file that we are intented to extract occupy about 30k tokens then there will be no token left for the model itself to reason and then extract the appropiate structure.


gemma4:e2b This model i started with the files that does not occupy that much, and the structured is correct but the fields of dose min max, and the days are null or not correct. Thus, the most complex fields like "resposta clinica" and "motiu discontinucio" it will also be null.


qwen3:8b This model trying with the file of "97966343" it takes like about for more thant 10 min. This file just got 2 visits about 2800 chars. The others models did not take that long. Lets see how is the result.



