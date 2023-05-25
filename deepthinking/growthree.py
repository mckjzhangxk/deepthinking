# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/growtree.ipynb.

# %% auto 0
__all__ = ['torch_device', 'tree_prompts', 'hparam', 'release_cache', 'image_grid', 'isColab', 'HiperParameter', 'pil2Latents',
           'latents2Pil', 'batchPil2Latents', 'batchLatents2Pil', 'generate_baseon_prompt_emb']

# %% ../nbs/growtree.ipynb 3
import torch,numpy as np,math,matplotlib.pyplot as plt
import torchvision.transforms as tfms
from diffusers import StableDiffusionPipeline,AutoencoderKL,UNet2DConditionModel,LMSDiscreteScheduler
from transformers import CLIPTokenizer,CLIPTextModel
from PIL import Image
import gc,os
from tqdm.auto import tqdm
from dataclasses import dataclass
from functools import partial

# %% ../nbs/growtree.ipynb 5
torch_device = "cuda" if torch.cuda.is_available() else "cpu"

def release_cache():
    gc.collect()
    torch.cuda.empty_cache()
#把图片排成 rows,cols的网格中，先排cols,后排rows
#其中len(imgs)=cols x rows
def image_grid(imgs, rows, cols):
    w,h = imgs[0].size
    grid = Image.new('RGB', size=(cols*w, rows*h))
    for i, img in enumerate(imgs): grid.paste(img, box=(i%cols*w, i//cols*h))
    return grid
def isColab():
    try:
        import google.colab
        IN_COLAB = True
    except:
        IN_COLAB = False
    if IN_COLAB:
        print("当前环境是Colab")
    else:
        print("当前环境不是Colab")
    return IN_COLAB
isColab(),torch_device

# %% ../nbs/growtree.ipynb 7
@dataclass
class HiperParameter():
    prompts:tuple
    fps:int=1
    prompt_per_second:int=1
    
    seed=1000
    guide_factor:int=7.5
    num_inference:int=5
    start_step:int=0
    
    output_dir='grow_output'
tree_prompts =(
    "An oak tree with bare branches in the winter snowing blizzard bleak",
    "A barren oak tree with no leaves and grass on the ground",
    "An oak tree in the spring with bright green leaves",
    "An oak tree in the summer with dark green leaves with a squirrel on the trunk",
    "An oak tree in the fall with colorful leaves on the ground",
    "An barren oak tree with no leaves in the fall leaves on the ground long shadows",
    "An oak tree with bare branches in the winter snowing blizzard bleak"
)
hparam=HiperParameter(prompts=tree_prompts)

# %% ../nbs/growtree.ipynb 11
@torch.no_grad()
def pil2Latents(input_image:Image)-> torch.FloatTensor:
    '''
    把图片转换成vae的输入，生成的tensor已经移torch_device上了
    返回：size=[1,4,64,64]
    '''
    def tfms2Latent(r):
        return 2*r-1
    ts=tfms.ToTensor()(input_image).unsqueeze(0)
    ts=tfms2Latent(ts).to(vae.device,dtype=vae.dtype)
    return 0.18215*vae.encode(ts).latent_dist.sample()
@torch.no_grad()
def latents2Pil(latents:torch.FloatTensor) ->Image:
    '''
    把隐变量还原成PIL.Image
    latents: FloatTensor,size=[1,4,64,64]
    '''
    def tfms2Img(r):
        r=(0.5*r+0.5)
        return r.float().clamp(0,1)
    decode_img=vae.decode(latents/0.18215).sample.detach().cpu()
    decode_img=decode_img.permute(0,2,3,1).squeeze()
    decode_img=tfms2Img(decode_img)

    arr_img=decode_img.numpy()*255
    arr_img=arr_img.astype('uint8')
    return Image.fromarray(arr_img)

@torch.no_grad()
def batchPil2Latents(imgs:list)-> torch.FloatTensor:
    '''
    批量把图片转换成vae的输入，生成的tensor已经移torch_device上了
    返回：size=[B,4,64,64]
    '''
    def tfms2Latent(r):
        return 2*r-1
    f=tfms.ToTensor()
    
    ts=torch.stack([f(img) for img in imgs])
    ts=tfms2Latent(ts).to(vae.device,dtype=vae.dtype)
    return 0.18215*vae.encode(ts).latent_dist.sample()
@torch.no_grad()
def batchLatents2Pil(latents:torch.FloatTensor) ->Image:
    '''
    批量把隐变量还原成PIL.Image
    latents: FloatTensor,size=[B,4,64,64]
    '''
    def tfms2Img(r):
        r=(0.5*r+0.5)
        return r.float().clamp(0,1)
    decode_imgs=vae.decode(latents/0.18215).sample.detach().cpu()
    decode_imgs=decode_imgs.permute(0,2,3,1)
    
    decode_imgs=tfms2Img(decode_imgs)

    arr_img=decode_imgs.numpy()*255
    arr_img=arr_img.astype('uint8')
    return [Image.fromarray(a) for a in arr_img]

# %% ../nbs/growtree.ipynb 17
def generate_baseon_prompt_emb(img_latent:torch.FloatTensor,token_emb:torch.FloatTensor,pbar=None)->(Image,torch.FloatTensor):
    '''
        :param token_emb: img_latent 图像的隐变量,(2,4,64,64)的tensor
        :param token_emb: 句子经过clip_encoder后的向量表示,(2,T,D) 
        :return:  denoise 后的图片
    '''
    if hparam.seed>=0:
        torch.manual_seed(hparam.seed)
    else:
        torch.seed()

    start_step=hparam.start_step
    schedular.set_timesteps(hparam.num_inference)
    
    init_noise=torch.randn_like(img_latent)
    img_latent=schedular.add_noise(img_latent,init_noise,schedular.timesteps[start_step:start_step+1])

    if pbar is None:
        pbar=tqdm(range(len(schedular.timesteps)))
    with torch.no_grad():
        for s in range(len(schedular.timesteps)):
            if s>=start_step:
                t=schedular.timesteps[s]
                inp=torch.concat([img_latent,img_latent])
                inp=schedular.scale_model_input(inp,t)

                noise=unet(inp,t,encoder_hidden_states=token_emb).sample

                pred_noise=noise[0]+hparam.guide_factor*(noise[1]-noise[0])
                # pred_noise=pred_noise/pred_noise.norm()*noise[0].norm()
                img_latent=schedular.step(pred_noise,t,img_latent).prev_sample
            pbar.update(1)
    return latents2Pil(img_latent),img_latent
